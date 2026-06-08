from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, description="用户输入")
    conversation_id: str | None = None


class Source(BaseModel):
    title: str
    content: str


class AgentChatResponse(BaseModel):
    intent: str
    answer: str
    sources: list[Source] = []
    conversation_id: str | None = None
    needs_edu_login: bool = False
