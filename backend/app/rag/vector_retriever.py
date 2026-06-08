from app.db.postgres import get_connection
from app.llm.embedding import EmbeddingClient


async def search_oa_notices_by_vector(query: str, limit: int = 5) -> list[dict]:
    """向量检索 OA 通知 chunks，返回最相关的前 N 条"""
    client = EmbeddingClient()
    query_embedding = await client.embed_text(query)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    chunk_text,
                    metadata,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM oa_notice_chunks
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_embedding, query_embedding, limit),
            )
            rows = cur.fetchall()

    results = []
    for row in rows:
        results.append({
            "chunk_text": row["chunk_text"],
            "metadata": row["metadata"],
            "similarity": row["similarity"],
        })

    return results
