import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.agent.orchestrator import chat
from app.auth import get_optional_user
from app.schemas.agent import AgentChatRequest, AgentChatResponse

router = APIRouter(tags=["agent"])


@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(request: AgentChatRequest, user: dict | None = Depends(get_optional_user)):
    try:
        return await chat(request, user=user)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
