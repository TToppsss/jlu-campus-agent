from __future__ import annotations

import json
from datetime import date
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.agent.memory import chat_memory
from app.agent.query_rewriter import rewrite_query
from app.agent.web_search import search_web
from app.edu.client import SessionExpiredError
from app.edu.schedule import query_schedule
from app.edu.session import edu_session_store
from app.llm.client import DeepSeekClient
from app.rag.oa_retrieval import search_oa_references
from app.rag.retriever import get_retriever
from app.schemas.agent import AgentChatRequest, AgentChatResponse, Source

AGENT_SYSTEM_PROMPT = """
你是吉林大学校园生活智能体（吉大校园智能体）。

当前日期：{current_date}

你负责统一理解用户问题，并决定是否调用工具获取资料后再回答。

可用能力：
- 查询吉林大学 OA 校内通知
- 查询本地校园知识库
- 联网搜索公开实时信息
- 查询当前用户的教务课表（需要用户已登录教务系统）
- 直接进行普通对话

回答原则：
1. 如果用户只是问候、闲聊或一般常识问题，可以直接回答，不要调用工具。
2. 涉及吉林大学 OA 通知、公告、申报、评奖、活动、讲座、部门通知时，优先调用 search_oa_notices。
3. 涉及校园卡、缓考、奖学金、大创、办事流程等本地知识库内容时，调用 search_campus_rag。
4. 涉及实时公开信息、外部网页、当前新闻或本地资料不足时，可以调用 web_search。
5. 不要为以下问题调用 web_search：当前日期、星期几、问候、闲聊、可由 system prompt 已知信息回答的问题。
6. 涉及"我的课表 / 这周课表 / 今天有什么课 / 下午有什么课 / 某天上什么课"等查询当前学生本人课表的问题，调用 get_my_schedule。
7. 如果调用教务工具时返回 status=login_required，说明用户尚未登录教务系统，请友好提示用户点击页面上的"登录教务"按钮完成登录后再问。
8. 可以根据需要一次调用多个工具，并综合工具返回结果回答。
9. 当工具返回结果中包含【参考资料】格式时，最终回答必须严格基于这些参考资料：
   - 不要编造任何参考资料中未提到的信息
   - 引用具体内容时使用 [1]、[2] 编号标注
   - 多条来源同时支撑同一句话时使用 [1][3]
   - 只引用真正使用到的资料编号，不要使用不存在的编号
   - 如果资料不足以回答，请明确说明"根据现有资料，暂时无法回答该问题"
10. 使用简体中文，回答简洁、可执行。
""".strip()

GROUNDED_ANSWER_PROMPT = """
你是吉林大学校园生活智能体。

你的任务是基于下方【参考资料】回答用户的问题。

请严格遵守以下规则：
1. 只基于【参考资料】中的内容回答问题，不要使用你自己的知识。
2. 如果【参考资料】中没有足够的信息来回答用户的问题，请明确回答："根据现有资料，暂时无法回答该问题。"
3. 不要编造任何【参考资料】中没有提到的信息，包括数字、日期、金额等具体细节。
4. 回答时请引用参考资料的编号，格式为 [1]、[2] 等，标注在相关句子的末尾。
5. 如果一句话的信息来自多条参考资料，请同时标注多个编号，如 [1][3]。
6. 只引用你实际使用到的参考资料，不要引用与回答无关的资料。
7. 如果多条参考资料的信息存在冲突，请指出冲突并告知用户以最新的资料为准。
8. 用简洁、友好的语气回答，避免过于官方或生硬的表述。

{references}

用户问题：{user_query}
""".strip()

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_oa_notices",
            "description": "查询吉林大学电子校务平台 OA 校内通知，适合通知、公告、申报、评奖、活动、讲座、项目、部门发布等问题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "用于检索 OA 通知的查询词"},
                    "limit": {"type": "integer", "description": "返回结果数量，默认 8"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_campus_rag",
            "description": "查询本地校园知识库，适合校园卡、缓考、奖学金、大创、创新创业、办事流程、材料要求等固定校园问答。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "用于检索校园知识库的查询词"},
                    "limit": {"type": "integer", "description": "返回结果数量，默认 4"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网搜索公开实时信息。普通问候、闲聊、常识问答不要调用；只有需要外部实时信息或本地资料不足时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "精炼后的联网搜索关键词"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_schedule",
            "description": "查询当前登录用户在吉林大学教务系统中的本学期课表。仅在用户问'我的课表/这周课表/今天有什么课/下午什么课'等本人课表问题时调用。需要用户已登录教务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "xnxq": {
                        "type": "string",
                        "description": "学年学期代码，如 2025-2026-2，留空表示当前学期",
                    },
                },
            },
        },
    },
]


class AgentState(TypedDict):
    messages: list[dict[str, Any]]
    sources: list[dict[str, str]]
    tool_rounds: int
    original_query: str
    rewritten_query: str
    use_grounded_prompt: bool
    user_id: str | None
    needs_edu_login: bool


def _load_arguments(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _source_key(source: dict[str, str]) -> tuple[str, str]:
    return source.get("title", ""), source.get("content", "")


def _merge_sources(existing: list[dict[str, str]], new_sources: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = {_source_key(source) for source in existing}
    merged = [*existing]
    for source in new_sources:
        key = _source_key(source)
        if key not in seen:
            seen.add(key)
            merged.append(source)
    return merged


async def _run_search_oa_notices(arguments: dict[str, Any], original_query: str) -> tuple[dict[str, Any], list[dict[str, str]], bool]:
    query = str(arguments.get("query") or original_query)
    limit = int(arguments.get("limit") or 8)
    result, sources = await search_oa_references(query, limit=limit)
    use_grounded = True
    return result, sources, use_grounded


async def _run_search_campus_rag(arguments: dict[str, Any], original_query: str) -> tuple[dict[str, Any], list[dict[str, str]], bool]:
    query = str(arguments.get("query") or original_query)
    limit = int(arguments.get("limit") or 4)
    chunks = get_retriever().search(query, limit=limit)
    sources = [{"title": chunk.source, "content": chunk.content} for chunk in chunks]

    lines = ["【参考资料】"]
    for index, chunk in enumerate(chunks, start=1):
        content = chunk.content.strip()
        if len(content) > 900:
            content = content[:900] + "..."
        lines.append(f"[{index}] 来源：{chunk.source}\n{content}")

    result = {
        "mode": "campus_rag",
        "query": query,
        "count": len(chunks),
        "references": "\n\n".join(lines),
    }
    use_grounded = True
    return result, sources, use_grounded


async def _run_web_search(arguments: dict[str, Any], original_query: str) -> tuple[dict[str, Any], list[dict[str, str]], bool]:
    query = str(arguments.get("query") or original_query)
    results = await search_web(query)
    payload = [
        {
            "title": item.title,
            "url": item.url,
            "snippet": item.snippet,
        }
        for item in results
    ]
    sources = [{"title": item.title, "content": item.url} for item in results]
    return {"query": query, "results": payload}, sources, False


async def _run_get_my_schedule(
    arguments: dict[str, Any], user_id: str | None
) -> tuple[dict[str, Any], list[dict[str, str]], bool]:
    print(f"[get_my_schedule] called with user_id={user_id} arguments={arguments}", flush=True)
    if not user_id:
        print(f"[get_my_schedule] user_id is None, returning login_required", flush=True)
        return {"status": "login_required", "reason": "未登录应用账号"}, [], False
    session = await edu_session_store.load_session(user_id)
    print(f"[get_my_schedule] loaded session: {bool(session)} (user_id={user_id})", flush=True)
    if not session:
        print(f"[get_my_schedule] no session in Redis for user_id={user_id}", flush=True)
        return {"status": "login_required", "reason": "尚未登录吉林大学教务系统"}, [], True
    cookies = session.get("cookies") or {}
    print(f"[get_my_schedule] cookies keys: {list(cookies.keys())}", flush=True)
    print(f"[get_my_schedule] _WEU type: {type(cookies.get('_WEU'))}, value preview: {str(cookies.get('_WEU'))[:100]}", flush=True)
    xnxq = arguments.get("xnxq") or None
    print(f"[get_my_schedule] querying schedule with {len(cookies)} cookies, xnxq={xnxq}", flush=True)
    try:
        result = await query_schedule(cookies, xnxq=xnxq)
        print(f"[get_my_schedule] query succeeded, got {result.get('total', 0)} courses", flush=True)
    except SessionExpiredError as exc:
        print(f"[edu_schedule] query failed with SessionExpiredError user_id={user_id}; keeping Redis session", flush=True)
        return {"status": "error", "reason": "教务接口暂时认为登录态不可用，但 Redis 中仍保留登录态，请稍后重试"}, [], False
    except Exception as exc:
        print(f"[get_my_schedule] query failed with exception: {type(exc).__name__}: {exc}", flush=True)
        return {"status": "error", "reason": f"查询课表失败：{exc}"}, [], False
    await edu_session_store.save_session(user_id, cookies, userid=session.get("userid"))
    return {"status": "ok", **result}, [], False


async def _agent_node(state: AgentState) -> AgentState:
    client = DeepSeekClient()
    reply = await client.chat_with_tools(messages=state["messages"], tools=TOOLS)
    return {**state, "messages": [*state["messages"], reply]}


async def _tools_node(state: AgentState) -> AgentState:
    last_message = state["messages"][-1]
    tool_calls = last_message.get("tool_calls") or []
    messages = [*state["messages"]]
    sources = [*state["sources"]]
    use_grounded = state.get("use_grounded_prompt", False)
    needs_edu_login = state.get("needs_edu_login", False)

    for call in tool_calls:
        function = call.get("function") or {}
        name = function.get("name")
        arguments = _load_arguments(function.get("arguments"))
        try:
            if name == "search_oa_notices":
                payload, new_sources, grounded = await _run_search_oa_notices(arguments, state["original_query"])
                use_grounded = use_grounded or grounded
            elif name == "search_campus_rag":
                payload, new_sources, grounded = await _run_search_campus_rag(arguments, state["original_query"])
                use_grounded = use_grounded or grounded
            elif name == "web_search":
                payload, new_sources, grounded = await _run_web_search(arguments, state["original_query"])
                use_grounded = use_grounded or grounded
            elif name == "get_my_schedule":
                payload, new_sources, login_signal = await _run_get_my_schedule(arguments, state.get("user_id"))
                if login_signal:
                    needs_edu_login = True
            else:
                payload, new_sources = {"error": f"unknown tool {name}"}, []
        except Exception as exc:
            payload, new_sources = {"error": str(exc)}, []

        sources = _merge_sources(sources, new_sources)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.get("id"),
                "content": json.dumps(payload, ensure_ascii=False),
            }
        )

    return {
        "messages": messages,
        "sources": sources,
        "tool_rounds": state["tool_rounds"] + 1,
        "original_query": state["original_query"],
        "rewritten_query": state["rewritten_query"],
        "use_grounded_prompt": use_grounded,
        "user_id": state.get("user_id"),
        "needs_edu_login": needs_edu_login,
    }


def _should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if state["tool_rounds"] >= 3:
        return END
    if last_message.get("tool_calls"):
        return "tools"
    return END


def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("agent", _agent_node)
    graph.add_node("tools", _tools_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", _should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


async def run_agent_chat(request: AgentChatRequest, user_id: str | None) -> AgentChatResponse:
    client = DeepSeekClient()
    if not client.is_configured:
        return AgentChatResponse(
            intent="direct_chat",
            answer="DeepSeek API Key 未配置，暂时无法调用智能体。",
            sources=[],
            conversation_id=request.conversation_id,
            needs_edu_login=False,
        )

    conversation_id = request.conversation_id
    if user_id and not conversation_id:
        meta = await chat_memory.create_conversation(user_id)
        conversation_id = meta["id"]

    memory = await chat_memory.load(user_id, conversation_id)
    current_date_str = date.today().isoformat()

    rewrite_result = await rewrite_query(request.message, memory, current_date_str)
    primary_query = rewrite_result.get("queries", [{}])[0]
    rewritten_query_text = primary_query.get("query", request.message)

    app = build_agent_graph()
    system_content = AGENT_SYSTEM_PROMPT.format(current_date=current_date_str)

    messages_with_memory = [{"role": "system", "content": system_content}]
    if memory.get("summary"):
        messages_with_memory.append({"role": "system", "content": f"【对话背景摘要】{memory['summary']}"})
    for msg in memory.get("messages", []):
        role = msg.get("role")
        content = msg.get("content") or ""
        if role in ("user", "assistant") and content:
            messages_with_memory.append({"role": role, "content": content})

    messages_with_memory.append({"role": "user", "content": request.message})

    initial_state: AgentState = {
        "messages": messages_with_memory,
        "sources": [],
        "tool_rounds": 0,
        "original_query": request.message,
        "rewritten_query": rewritten_query_text,
        "use_grounded_prompt": False,
        "user_id": user_id,
        "needs_edu_login": False,
    }

    final_state = await app.ainvoke(initial_state)
    final_message = final_state["messages"][-1]
    answer = final_message.get("content") or "我没有生成有效回答，请换一种问法再试。"
    raw_sources = final_state["sources"][:8]
    sources = [Source(title=item["title"], content=item["content"]) for item in raw_sources]

    await chat_memory.save_turn(user_id, conversation_id, request.message, answer, sources=raw_sources)

    return AgentChatResponse(
        intent="agent_chat",
        answer=answer,
        sources=sources,
        conversation_id=conversation_id,
        needs_edu_login=bool(final_state.get("needs_edu_login")),
    )
