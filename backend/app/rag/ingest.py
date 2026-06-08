import json

from app.db.postgres import get_connection
from app.llm.embedding import EmbeddingClient
from app.rag.chunker import extract_keywords, recursive_chunk


async def ingest_notice(notice_id: int, title: str, url: str, publish_date: str, content: str) -> int:
    """分块、embed、入库单条通知，返回写入的 chunk 数量"""
    if not content or len(content) < 10:
        return 0

    chunks = recursive_chunk(content, chunk_size=150, overlap=15)
    if not chunks:
        return 0

    client = EmbeddingClient()
    embeddings = await client.embed_batch(chunks)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM oa_notice_chunks WHERE notice_id = %s", (notice_id,))
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                keywords = extract_keywords(chunk, max_keywords=5)
                metadata = {
                    "notice_id": notice_id,
                    "title": title,
                    "url": url,
                    "publish_date": publish_date,
                    "chunk_index": i,
                    "keywords": keywords,
                }
                # 确保 embedding 全是 float 类型
                embedding_floats = [float(x) for x in embedding]
                cur.execute(
                    """
                    INSERT INTO oa_notice_chunks (notice_id, chunk_index, chunk_text, embedding, metadata)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (notice_id, chunk_index) DO UPDATE SET
                        chunk_text = EXCLUDED.chunk_text,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata
                    """,
                    (notice_id, i, chunk, embedding_floats, json.dumps(metadata, ensure_ascii=False)),
                )

    return len(chunks)


async def ingest_notices_by_ids(notice_ids: list[int]) -> dict[str, int]:
    if not notice_ids:
        return {"notices": 0, "chunks": 0}

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, title, url, publish_date, content
                FROM oa_notices
                WHERE id = ANY(%s) AND content IS NOT NULL AND content != ''
                """,
                (notice_ids,),
            )
            notices = cur.fetchall()

    total_chunks = 0
    for notice in notices:
        notice_id = notice["id"]
        title = notice["title"]
        url = notice["url"]
        publish_date = str(notice["publish_date"]) if notice["publish_date"] else ""
        content = notice["content"] or ""
        chunks_count = await ingest_notice(notice_id, title, url, publish_date, content)
        total_chunks += chunks_count

    return {"notices": len(notices), "chunks": total_chunks}


async def ingest_all_notices() -> dict[str, int]:
    """批量 ingest 所有 oa_notices 表里的通知"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, title, url, publish_date, content FROM oa_notices WHERE content IS NOT NULL AND content != ''")
            notices = cur.fetchall()

    total_notices = len(notices)
    total_chunks = 0

    for notice in notices:
        notice_id = notice["id"]
        title = notice["title"]
        url = notice["url"]
        publish_date = str(notice["publish_date"]) if notice["publish_date"] else ""
        content = notice["content"] or ""
        chunks_count = await ingest_notice(notice_id, title, url, publish_date, content)
        total_chunks += chunks_count

    return {"notices": total_notices, "chunks": total_chunks}
