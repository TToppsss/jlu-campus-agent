from __future__ import annotations

from pydantic import BaseModel, Field


class AuthRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
