from __future__ import annotations

import json
from typing import Any

from app.llm.client import DeepSeekClient

QUERY_REWRITE_PROMPT = """
你是一个校园智能体的查询改写助手。根据对话历史和用户最新问题，将问题改写为适合检索的查询。

要求：
1. 补全代词、省略上下文和相对日期。
2. 将口语化表达转成正式检索表达。
3. 如果包含多个独立意图，拆分为多个子查询。
4. 输出 JSON，不要输出解释。

JSON 格式：
{
  "queries": [
    {
      "query": "适合检索的查询",
      "type": "oa_notice|campus_rag|web|general",
      "date": "YYYY-MM-DD 或空字符串",
      "keywords": ["关键词"]
    }
  ]
}
""".strip()


def _history_text(memory: dict[str, Any]) -> str:
    lines: list[str] = []
    summary = memory.get("summary") or ""
    if summary:
        lines.append(f"摘要：{summary}")
    for message in memory.get("messages") or []:
        role = message.get("role") or ""
        content = message.get("content") or ""
        if role and content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) or "无"


async def rewrite_query(user_query: str, memory: dict[str, Any], current_date: str) -> dict[str, Any]:
    fallback = {"queries": [{"query": user_query, "type": "general", "date": "", "keywords": []}]}

    client = DeepSeekClient()
    if not client.is_configured:
        return fallback

    try:
        content = await client.chat_json(
            [
                {"role": "system", "content": QUERY_REWRITE_PROMPT},
                {
                    "role": "user",
                    "content": f"当前日期：{current_date}\n\n对话历史：\n{_history_text(memory)}\n\n用户最新问题：{user_query}",
                },
            ],
            temperature=0.1,
        )
    except Exception as exc:
        print(f"[query_rewriter] LLM 调用失败：{exc}", flush=True)
        return fallback

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        print(f"[query_rewriter] JSON 解析失败：{exc}", flush=True)
        return fallback

    queries = data.get("queries")
    if not isinstance(queries, list) or not queries:
        return fallback

    cleaned_queries: list[dict[str, Any]] = []
    for item in queries:
        if not isinstance(item, dict):
            continue
        cleaned_queries.append(
            {
                "query": str(item.get("query") or user_query),
                "type": str(item.get("type") or "general"),
                "date": str(item.get("date") or ""),
                "keywords": list(item.get("keywords") or []),
            }
        )
    if not cleaned_queries:
        return fallback
    return {"queries": cleaned_queries}
