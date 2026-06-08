from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.agent.memory import chat_memory
from app.auth import get_optional_user
from pydantic import BaseModel, Field

router = APIRouter(tags=["conversations"])


class ConversationCreate(BaseModel):
    title: str | None = None


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=80)


def _require_user_id(user: dict | None) -> str:
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return str(user["sub"])


@router.get("")
async def list_conversations(user: dict | None = Depends(get_optional_user)):
    user_id = _require_user_id(user)
    return await chat_memory.list_conversations(user_id)


@router.post("")
async def create_conversation(payload: ConversationCreate, user: dict | None = Depends(get_optional_user)):
    user_id = _require_user_id(user)
    return await chat_memory.create_conversation(user_id, payload.title)


@router.get("/{conversation_id}/messages")
async def get_messages(conversation_id: str, user: dict | None = Depends(get_optional_user)):
    user_id = _require_user_id(user)
    data = await chat_memory.load(user_id, conversation_id)
    return {
        "summary": data["summary"],
        "messages": data["messages"],
    }


@router.patch("/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    payload: ConversationRename,
    user: dict | None = Depends(get_optional_user),
):
    user_id = _require_user_id(user)
    await chat_memory.rename_conversation(user_id, conversation_id, payload.title)
    return {"status": "ok"}


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str, user: dict | None = Depends(get_optional_user)):
    user_id = _require_user_id(user)
    await chat_memory.delete_conversation(user_id, conversation_id)
    return {"status": "ok"}
