from __future__ import annotations

import json
import time
from typing import Any

import redis.asyncio as redis

from app.config import settings


def _session_key(app_user_id: str) -> str:
    return f"edu:session:{app_user_id}"


def _pending_key(app_user_id: str) -> str:
    return f"edu:pending:{app_user_id}"


class EduSessionStore:
    """教务系统登录态 Redis 管理。

    - session: 登录成功后的业务 cookies（route + GS_SESSIONID + JSESSIONID 等），永不过期，靠手动管理
    - pending: 第一步登录后到第二步确认前的中间状态（lt + cas cookies + 用户名），5 分钟过期
    """

    def __init__(self) -> None:
        self.client = redis.from_url(settings.redis_url, decode_responses=True)

    # ---- pending（登录中间态） ----
    async def save_pending(self, app_user_id: str, payload: dict[str, Any]) -> None:
        await self.client.set(_pending_key(app_user_id), json.dumps(payload, ensure_ascii=False), ex=300)

    async def load_pending(self, app_user_id: str) -> dict[str, Any] | None:
        raw = await self.client.get(_pending_key(app_user_id))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def delete_pending(self, app_user_id: str) -> None:
        await self.client.delete(_pending_key(app_user_id))

    # ---- session（已登录的业务 cookies） ----
    async def save_session(self, app_user_id: str, cookies: dict[str, str], userid: str | None = None) -> None:
        payload = {
            "cookies": cookies,
            "userid": userid or "",
            "logged_in_at": int(time.time()),
            "last_refreshed_at": int(time.time()),
        }
        await self.client.set(_session_key(app_user_id), json.dumps(payload, ensure_ascii=False))

    async def load_session(self, app_user_id: str) -> dict[str, Any] | None:
        raw = await self.client.get(_session_key(app_user_id))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def update_refreshed_at(self, app_user_id: str) -> None:
        data = await self.load_session(app_user_id)
        if not data:
            return
        data["last_refreshed_at"] = int(time.time())
        await self.client.set(_session_key(app_user_id), json.dumps(data, ensure_ascii=False))

    async def delete_session(self, app_user_id: str, reason: str = "") -> None:
        reason_text = f" reason={reason}" if reason else ""
        print(f"[edu_session] delete_session user_id={app_user_id}{reason_text}", flush=True)
        await self.client.delete(_session_key(app_user_id))

    async def list_session_user_ids(self) -> list[str]:
        keys = await self.client.keys("edu:session:*")
        ids: list[str] = []
        prefix = "edu:session:"
        for key in keys:
            if key.startswith(prefix):
                ids.append(key[len(prefix):])
        return ids


edu_session_store = EduSessionStore()
