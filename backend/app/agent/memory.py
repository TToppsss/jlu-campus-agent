from __future__ import annotations

import json
import time
import uuid
from typing import Any

import redis.asyncio as redis

from app.config import settings
from app.llm.client import DeepSeekClient

HISTORY_CHAR_THRESHOLD = 4000
KEEP_RECENT_TURNS = 2
KEEP_RECENT_MESSAGES = KEEP_RECENT_TURNS * 2

SUMMARY_MERGE_PROMPT = """
你是一个对话摘要助手。请把【已有摘要】与【新增对话片段】合并为新的对话背景摘要。

要求：
1. 保留对未来对话有用的事实、用户画像（身份/学院/年级/校区等如果用户提到过）、未完成事项、关键细节。
2. 用一段简体中文，控制在 250 字以内。
3. 不要使用列表格式，输出一段连续的文字。
4. 不要重复无意义内容，不要编造信息。
""".strip()


def _conv_meta_key(user_id: str) -> str:
    return f"chat:user:{user_id}:conversations"


def _conv_messages_key(user_id: str, conversation_id: str) -> str:
    return f"chat:user:{user_id}:conv:{conversation_id}:messages"


def _conv_summary_key(user_id: str, conversation_id: str) -> str:
    return f"chat:user:{user_id}:conv:{conversation_id}:summary"


async def _summarize(old_summary: str, dropped_messages: list[dict[str, str]]) -> str:
    if not dropped_messages:
        return old_summary

    fragment_lines = [f"{msg.get('role', '')}: {msg.get('content', '')}" for msg in dropped_messages]
    fragment = "\n".join(fragment_lines)

    fallback = (old_summary + " " + fragment[:600]).strip()[:600]

    client = DeepSeekClient()
    if not client.is_configured:
        return fallback

    try:
        content = await client.chat_text(
            [
                {"role": "system", "content": SUMMARY_MERGE_PROMPT},
                {
                    "role": "user",
                    "content": f"【已有摘要】\n{old_summary or '无'}\n\n【新增对话片段】\n{fragment}",
                },
            ],
            temperature=0.2,
        )
        return content.strip() or fallback
    except Exception:
        return fallback


def _messages_char_size(messages: list[dict[str, Any]]) -> int:
    return sum(len(msg.get("content") or "") for msg in messages)


class ChatMemory:
    def __init__(self) -> None:
        self.client = redis.from_url(settings.redis_url, decode_responses=True)

    async def list_conversations(self, user_id: str) -> list[dict[str, Any]]:
        raw = await self.client.hgetall(_conv_meta_key(user_id))
        items: list[dict[str, Any]] = []
        for cid, payload in raw.items():
            try:
                meta = json.loads(payload)
            except json.JSONDecodeError:
                continue
            items.append({"id": cid, **meta})
        items.sort(key=lambda item: item.get("updated_at", 0), reverse=True)
        return items

    async def create_conversation(self, user_id: str, title: str | None = None) -> dict[str, Any]:
        cid = uuid.uuid4().hex[:12]
        now = int(time.time())
        meta = {"title": title or "新对话", "created_at": now, "updated_at": now}
        await self.client.hset(_conv_meta_key(user_id), cid, json.dumps(meta, ensure_ascii=False))
        await self.client.expire(_conv_meta_key(user_id), settings.chat_memory_ttl_seconds)
        return {"id": cid, **meta}

    async def rename_conversation(self, user_id: str, conversation_id: str, title: str) -> None:
        meta_key = _conv_meta_key(user_id)
        raw = await self.client.hget(meta_key, conversation_id)
        if not raw:
            return
        try:
            meta = json.loads(raw)
        except json.JSONDecodeError:
            meta = {}
        meta["title"] = title
        meta["updated_at"] = int(time.time())
        await self.client.hset(meta_key, conversation_id, json.dumps(meta, ensure_ascii=False))

    async def delete_conversation(self, user_id: str, conversation_id: str) -> None:
        await self.client.hdel(_conv_meta_key(user_id), conversation_id)
        await self.client.delete(
            _conv_messages_key(user_id, conversation_id),
            _conv_summary_key(user_id, conversation_id),
        )

    async def load(self, user_id: str | None, conversation_id: str | None) -> dict[str, Any]:
        if not user_id or not conversation_id:
            return {"summary": "", "messages": []}
        summary = await self.client.get(_conv_summary_key(user_id, conversation_id)) or ""
        raw_items = await self.client.lrange(_conv_messages_key(user_id, conversation_id), 0, -1)
        messages: list[dict[str, Any]] = []
        for raw in raw_items:
            try:
                messages.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        return {"summary": summary, "messages": messages}

    async def _update_meta(self, user_id: str, conversation_id: str, sample_user_message: str | None) -> None:
        meta_key = _conv_meta_key(user_id)
        raw_meta = await self.client.hget(meta_key, conversation_id)
        meta = json.loads(raw_meta) if raw_meta else {"title": "新对话", "created_at": int(time.time())}
        meta["updated_at"] = int(time.time())
        if (meta.get("title") or "新对话") == "新对话" and sample_user_message:
            meta["title"] = sample_user_message.strip().splitlines()[0][:24] or "新对话"
        await self.client.hset(meta_key, conversation_id, json.dumps(meta, ensure_ascii=False))
        await self.client.expire(meta_key, settings.chat_memory_ttl_seconds)

    async def save_turn(
        self,
        user_id: str | None,
        conversation_id: str | None,
        user_message: str,
        assistant_message: str,
        sources: list[dict[str, str]] | None = None,
    ) -> None:
        if not user_id or not conversation_id:
            return

        msg_key = _conv_messages_key(user_id, conversation_id)
        summary_key = _conv_summary_key(user_id, conversation_id)
        ttl = settings.chat_memory_ttl_seconds

        user_msg = {"role": "user", "content": user_message, "ts": int(time.time())}
        assistant_msg = {
            "role": "assistant",
            "content": assistant_message,
            "sources": sources or [],
            "ts": int(time.time()),
        }
        await self.client.rpush(
            msg_key,
            json.dumps(user_msg, ensure_ascii=False),
            json.dumps(assistant_msg, ensure_ascii=False),
        )
        await self.client.expire(msg_key, ttl)

        raw_items = await self.client.lrange(msg_key, 0, -1)
        messages: list[dict[str, Any]] = []
        for raw in raw_items:
            try:
                messages.append(json.loads(raw))
            except json.JSONDecodeError:
                continue

        if _messages_char_size(messages) > HISTORY_CHAR_THRESHOLD and len(messages) > KEEP_RECENT_MESSAGES:
            to_compress = messages[:-KEEP_RECENT_MESSAGES]
            keep = messages[-KEEP_RECENT_MESSAGES:]
            simple_dropped = [{"role": m.get("role", ""), "content": m.get("content") or ""} for m in to_compress]
            old_summary = await self.client.get(summary_key) or ""
            new_summary = await _summarize(old_summary, simple_dropped)
            await self.client.set(summary_key, new_summary, ex=ttl)
            await self.client.delete(msg_key)
            if keep:
                await self.client.rpush(msg_key, *[json.dumps(m, ensure_ascii=False) for m in keep])
                await self.client.expire(msg_key, ttl)
            messages = keep

        first_user = next((m for m in messages if m.get("role") == "user"), None)
        await self._update_meta(user_id, conversation_id, first_user.get("content") if first_user else None)


chat_memory = ChatMemory()
