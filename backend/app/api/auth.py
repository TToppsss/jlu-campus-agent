from __future__ import annotations

from fastapi import APIRouter

from app.auth import login_user, register_user
from app.schemas.auth import AuthRequest, AuthResponse

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=AuthResponse)
def register(request: AuthRequest) -> AuthResponse:
    return register_user(request)


@router.post("/login", response_model=AuthResponse)
def login(request: AuthRequest) -> AuthResponse:
    return login_user(request)
