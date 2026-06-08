import json
from typing import Any

from app.agent.web_search import WebSearchResult, search_web
from app.llm.client import DeepSeekClient

DIRECT_CHAT_SYSTEM_PROMPT = """
你是吉林大学校园生活智能体（吉大校园智能体）。

你的角色：
- 面向吉林大学学生，提供校园生活相关的帮助
- 性格友好、自然、口语化，像一个熟悉学校的同学
- 使用简体中文回答

回答原则：
1. 当用户只是打招呼、闲聊（如"你好""你是谁""能做什么"），直接以校园助手的身份自然回答，不要联网搜索。
2. 当用户问的问题需要外部、实时、具体的信息（比如新闻、热点、外部网址、外部资料、不在你知识范围内的事实），可以调用 web_search 工具联网查询。
3. 当用户问的问题你直接知道答案（比如校园生活常识、Python 怎么写、一般性知识），直接回答即可，不要联网。
4. 不要编造校园通知、教务规定等具体政策细节。如果不确定，建议用户去吉林大学电子校务平台或学院官网查证。
5. 回答要简洁直接，不要复述用户的问题。
""".strip()


WEB_SEARCH_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "当用户的问题需要外部实时信息或具体网址、资料时，调用此工具进行联网搜索。普通问候、闲聊、常识问答不要调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "用于联网搜索的关键词，应当是精炼的查询词，而不是用户的整句话。",
                },
            },
            "required": ["query"],
        },
    },
}


async def run_direct_chat(message: str) -> tuple[str, list[WebSearchResult]]:
    client = DeepSeekClient()
    if not client.is_configured:
        return "（DeepSeek API Key 未配置）你好，我是吉林大学校园智能体。", []

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": DIRECT_CHAT_SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]

    used_results: list[WebSearchResult] = []

    for _ in range(3):
        reply = await client.chat_with_tools(messages=messages, tools=[WEB_SEARCH_TOOL_SCHEMA])
        tool_calls = reply.get("tool_calls") or []
        if not tool_calls:
            return reply.get("content") or "", used_results

        messages.append(reply)
        for call in tool_calls:
            function = call.get("function") or {}
            name = function.get("name")
            arguments_raw = function.get("arguments") or "{}"
            try:
                arguments = json.loads(arguments_raw)
            except json.JSONDecodeError:
                arguments = {}
            tool_output = ""
            if name == "web_search":
                query = arguments.get("query") or message
                try:
                    results = await search_web(query)
                except Exception as exc:
                    tool_output = json.dumps({"error": str(exc)}, ensure_ascii=False)
                else:
                    used_results.extend(results)
                    tool_output = json.dumps(
                        [
                            {"title": item.title, "url": item.url, "snippet": item.snippet}
                            for item in results
                        ],
                        ensure_ascii=False,
                    )
            else:
                tool_output = json.dumps({"error": f"unknown tool {name}"}, ensure_ascii=False)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": tool_output,
                }
            )

    final = await client.chat_text(messages=[{"role": "system", "content": DIRECT_CHAT_SYSTEM_PROMPT}, {"role": "user", "content": message}])
    return final, used_results
