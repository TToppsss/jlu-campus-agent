from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from app.db.postgres import get_connection
from app.llm.embedding import EmbeddingClient

RRF_K = 60
DATE_RE_FULL = re.compile(r"(20\d{2})[-年./](\d{1,2})[-月./](\d{1,2})")
DATE_RE_SHORT = re.compile(r"(?<!\d)(\d{1,2})[-月./](\d{1,2})日?号?")
LIST_QUERY_KEYWORDS = (
    "通知",
    "公告",
    "发了什么",
    "有什么",
    "有哪些",
    "整理",
    "总结",
    "发布",
    "多少",
    "几篇",
    "几条",
)


def _embedding_literal(values: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def parse_query_date(query: str) -> date | None:
    if "今天" in query:
        return date.today()
    if "昨天" in query:
        return date.today() - timedelta(days=1)
    if "前天" in query:
        return date.today() - timedelta(days=2)

    match = DATE_RE_FULL.search(query)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    match = DATE_RE_SHORT.search(query)
    if match:
        month, day = (int(part) for part in match.groups())
        if 1 <= month <= 12 and 1 <= day <= 31:
            try:
                return date(date.today().year, month, day)
            except ValueError:
                return None
    return None


def is_notice_list_query(query: str) -> bool:
    target_date = parse_query_date(query)
    if not target_date:
        return False
    return any(keyword in query for keyword in LIST_QUERY_KEYWORDS)


def notices_by_publish_date(target_date: date, limit: int | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT id, title, url, source, publish_date, content
        FROM oa_notices
        WHERE publish_date = %s
        ORDER BY updated_at DESC, id DESC
    """
    params: tuple[Any, ...] = (target_date,)
    if limit is not None:
        sql += " LIMIT %s"
        params = (target_date, limit)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


async def vector_search_chunks(query: str, limit: int = 30) -> list[dict[str, Any]]:
    client = EmbeddingClient()
    query_embedding = _embedding_literal(await client.embed_text(query))

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    notice_id,
                    chunk_text,
                    metadata,
                    1 - (embedding <=> %s::vector) AS score
                FROM oa_notice_chunks
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_embedding, query_embedding, limit),
            )
            return list(cur.fetchall())


def keyword_search_chunks(query: str, limit: int = 30) -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT id, notice_id, chunk_text, metadata, paradedb.score(id) AS score
                    FROM oa_notice_chunks
                    WHERE chunk_text @@@ %s OR metadata @@@ %s
                    ORDER BY score DESC
                    LIMIT %s
                    """,
                    (query, query, limit),
                )
                return list(cur.fetchall())
            except Exception:
                conn.rollback()
                cur.execute(
                    """
                    SELECT id, notice_id, chunk_text, metadata, 1.0 AS score
                    FROM oa_notice_chunks
                    WHERE chunk_text ILIKE %s
                       OR metadata::text ILIKE %s
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (f"%{query}%", f"%{query}%", limit),
                )
                return list(cur.fetchall())


def rrf_fuse(result_sets: list[list[dict[str, Any]]], limit: int = 8) -> list[dict[str, Any]]:
    by_id: dict[int, dict[str, Any]] = {}
    scores: dict[int, float] = {}

    for rows in result_sets:
        for rank, row in enumerate(rows, start=1):
            chunk_id = int(row["id"])
            by_id.setdefault(chunk_id, row)
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (RRF_K + rank)

    ranked_ids = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)
    fused: list[dict[str, Any]] = []
    for chunk_id in ranked_ids[:limit]:
        row = dict(by_id[chunk_id])
        row["rrf_score"] = scores[chunk_id]
        fused.append(row)
    return fused


async def hybrid_search_oa_chunks(query: str, limit: int = 8, candidate_limit: int = 30) -> list[dict[str, Any]]:
    vector_rows = await vector_search_chunks(query, limit=candidate_limit)
    keyword_rows = keyword_search_chunks(query, limit=candidate_limit)
    return rrf_fuse([vector_rows, keyword_rows], limit=limit)


def format_references(items: list[dict[str, Any]], content_key: str = "content") -> tuple[str, list[dict[str, str]]]:
    lines = ["【参考资料】"]
    sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for index, item in enumerate(items, start=1):
        title = item.get("title") or item.get("source") or "OA 通知"
        publish_date = item.get("publish_date") or ""
        url = item.get("url") or ""
        content = (item.get(content_key) or item.get("chunk_text") or "").strip()
        if len(content) > 900:
            content = content[:900] + "..."
        lines.append(f"[{index}] 来源：{title} | 日期：{publish_date} | 链接：{url}\n{content}")
        if url and url not in seen_urls:
            seen_urls.add(url)
            sources.append({"title": str(title), "content": str(url)})

    return "\n\n".join(lines), sources


async def search_oa_references(query: str, limit: int = 8) -> tuple[dict[str, Any], list[dict[str, str]]]:
    target_date = parse_query_date(query)
    if target_date:
        notices = notices_by_publish_date(target_date)
        reference_text, sources = format_references(notices, content_key="content")
        return {
            "mode": "date_list",
            "query": query,
            "target_date": target_date.isoformat(),
            "count": len(notices),
            "references": reference_text,
        }, sources

    chunks = await hybrid_search_oa_chunks(query, limit=limit)
    normalized: list[dict[str, Any]] = []
    for row in chunks:
        metadata = row.get("metadata") or {}
        normalized.append(
            {
                "title": metadata.get("title") or "OA 通知",
                "url": metadata.get("url") or "",
                "publish_date": metadata.get("publish_date") or "",
                "chunk_text": row.get("chunk_text") or "",
                "rrf_score": row.get("rrf_score"),
            }
        )
    reference_text, sources = format_references(normalized, content_key="chunk_text")
    return {"mode": "hybrid_chunks", "query": query, "count": len(normalized), "references": reference_text}, sources
