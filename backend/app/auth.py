from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.db.postgres import get_connection
from app.schemas.auth import AuthRequest, AuthResponse

security = HTTPBearer(auto_error=False)


def init_auth_db() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )


def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_password_bytes(password), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, username: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "username": username, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def register_user(request: AuthRequest) -> AuthResponse:
    init_auth_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username = %s", (request.username,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="用户名已存在")
            cur.execute(
                """
                INSERT INTO users (username, password_hash)
                VALUES (%s, %s)
                RETURNING id
                """,
                (request.username, hash_password(request.password)),
            )
            user_id = int(cur.fetchone()["id"])
    return AuthResponse(access_token=create_access_token(user_id, request.username), username=request.username)


def login_user(request: AuthRequest) -> AuthResponse:
    init_auth_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, username, password_hash FROM users WHERE username = %s", (request.username,))
            user = cur.fetchone()
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return AuthResponse(access_token=create_access_token(int(user["id"]), user["username"]), username=user["username"])


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="登录状态无效或已过期") from exc


def get_optional_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict | None:
    if not credentials:
        return None
    return decode_token(credentials.credentials)
