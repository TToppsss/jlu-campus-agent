from dataclasses import dataclass
from datetime import date, datetime

import psycopg
from psycopg.rows import dict_row

from app.config import settings


@dataclass
class NoticeRecord:
    title: str
    url: str
    publish_date: date | None = None
    source: str = "吉林大学电子校务平台"
    content: str = ""
    fetched_at: datetime | None = None


def get_connection():
    return psycopg.connect(settings.database_url, row_factory=dict_row)


def init_db() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS oa_notices (
                    id BIGSERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL DEFAULT '吉林大学电子校务平台',
                    publish_date DATE,
                    content TEXT NOT NULL DEFAULT '',
                    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_oa_notices_publish_date ON oa_notices (publish_date DESC NULLS LAST)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_oa_notices_title_trgm_fallback ON oa_notices (title)"
            )


def upsert_notices_with_ids(records: list[NoticeRecord]) -> list[int]:
    if not records:
        return []

    init_db()
    changed_ids: list[int] = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            for record in records:
                cur.execute(
                    """
                    INSERT INTO oa_notices (title, url, source, publish_date, content, fetched_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, now(), now())
                    ON CONFLICT (url) DO UPDATE SET
                        title = EXCLUDED.title,
                        source = EXCLUDED.source,
                        publish_date = COALESCE(EXCLUDED.publish_date, oa_notices.publish_date),
                        content = CASE
                            WHEN EXCLUDED.content <> '' THEN EXCLUDED.content
                            ELSE oa_notices.content
                        END,
                        updated_at = now()
                    WHERE oa_notices.title IS DISTINCT FROM EXCLUDED.title
                       OR oa_notices.content IS DISTINCT FROM EXCLUDED.content
                       OR oa_notices.publish_date IS DISTINCT FROM COALESCE(EXCLUDED.publish_date, oa_notices.publish_date)
                    RETURNING id
                    """,
                    (record.title, record.url, record.source, record.publish_date, record.content),
                )
                row = cur.fetchone()
                if row:
                    changed_ids.append(int(row["id"]))
    return changed_ids


def upsert_notices(records: list[NoticeRecord]) -> int:
    return len(upsert_notices_with_ids(records))


def search_notices(query: str, limit: int = 8) -> list[dict]:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT title, url, source, publish_date, content,
                       ts_rank(search_vector, plainto_tsquery('simple', %s)) AS rank
                FROM oa_notices
                WHERE search_vector @@ plainto_tsquery('simple', %s)
                   OR title ILIKE %s
                   OR content ILIKE %s
                ORDER BY rank DESC NULLS LAST, publish_date DESC NULLS LAST, updated_at DESC
                LIMIT %s
                """,
                (query, query, f"%{query}%", f"%{query}%", limit),
            )
            return list(cur.fetchall())


def notices_by_date(target_date: date, limit: int = 20) -> list[dict]:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT title, url, source, publish_date, content
                FROM oa_notices
                WHERE publish_date = %s
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (target_date, limit),
            )
            return list(cur.fetchall())


def latest_notices(limit: int = 10) -> list[dict]:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT title, url, source, publish_date, content
                FROM oa_notices
                ORDER BY publish_date DESC NULLS LAST, updated_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return list(cur.fetchall())


def notice_count() -> int:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS count FROM oa_notices")
            return int(cur.fetchone()["count"])
