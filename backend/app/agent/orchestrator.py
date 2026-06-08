from pydantic import ValidationError

from app.agent.graph import run_agent_chat
from app.auth import get_optional_user
from app.schemas.agent import AgentChatRequest, AgentChatResponse


async def chat(request: AgentChatRequest, user: dict | None = None) -> AgentChatResponse:
    user_id = str(user["sub"]) if user else None
    try:
        return await run_agent_chat(request, user_id=user_id)
    except (ValueError, ValidationError) as exc:
        raise RuntimeError(f"模型返回格式异常：{exc}") from exc
