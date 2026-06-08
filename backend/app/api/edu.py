from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_optional_user
from app.edu.client import SessionExpiredError
from app.edu.login import (
    EduLoginError,
    confirm_login,
    fetch_userid,
    init_login,
    refresh_captcha,
    send_wechat_code,
)
from app.edu.schedule import query_schedule
from app.edu.session import edu_session_store

router = APIRouter(tags=["edu"])


class EduInitRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=4, max_length=128)


class EduSendWechatRequest(BaseModel):
    captcha_text: str = Field(min_length=1, max_length=12)


class EduConfirmRequest(BaseModel):
    wechat_code: str = Field(min_length=4, max_length=12)


def _require_user_id(user: dict | None) -> str:
    if not user:
        raise HTTPException(status_code=401, detail="未登录应用账号")
    return str(user["sub"])


@router.get("/status")
async def edu_status(user: dict | None = Depends(get_optional_user)):
    user_id = _require_user_id(user)
    data = await edu_session_store.load_session(user_id)
    if not data:
        return {"logged_in": False}
    return {
        "logged_in": True,
        "userid": data.get("userid") or "",
        "logged_in_at": data.get("logged_in_at"),
        "last_refreshed_at": data.get("last_refreshed_at"),
    }


@router.post("/login_init")
async def edu_login_init(payload: EduInitRequest, user: dict | None = Depends(get_optional_user)):
    user_id = _require_user_id(user)
    if await edu_session_store.load_session(user_id):
        raise HTTPException(status_code=409, detail="已登录教务系统，请先退出再重新登录")
    try:
        result = await init_login(payload.username, payload.password)
    except EduLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await edu_session_store.save_pending(user_id, result["pending"])
    return {"captcha_image": result["captcha_image"]}


@router.post("/login_refresh_captcha")
async def edu_login_refresh_captcha(user: dict | None = Depends(get_optional_user)):
    user_id = _require_user_id(user)
    pending = await edu_session_store.load_pending(user_id)
    if not pending:
        raise HTTPException(status_code=410, detail="登录会话已过期，请重新输入账号密码")
    try:
        result = await refresh_captcha(pending)
    except EduLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await edu_session_store.save_pending(user_id, result["pending"])
    return {"captcha_image": result["captcha_image"]}


@router.post("/login_send_wechat")
async def edu_login_send_wechat(
    payload: EduSendWechatRequest, user: dict | None = Depends(get_optional_user)
):
    user_id = _require_user_id(user)
    pending = await edu_session_store.load_pending(user_id)
    if not pending:
        raise HTTPException(status_code=410, detail="登录会话已过期，请重新输入账号密码")
    try:
        result = await send_wechat_code(pending, payload.captcha_text)
    except EduLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await edu_session_store.save_pending(user_id, result["pending"])
    return {"status": "wechat_sent"}


@router.post("/login_confirm")
async def edu_login_confirm(
    payload: EduConfirmRequest, user: dict | None = Depends(get_optional_user)
):
    user_id = _require_user_id(user)
    pending = await edu_session_store.load_pending(user_id)
    if not pending:
        raise HTTPException(status_code=410, detail="登录会话已过期，请重新发起登录")
    try:
        print(f"[edu_login_confirm] pending execution={pending.get('execution')}, captcha_code={pending.get('captcha_code')}", flush=True)
        biz_cookies = await confirm_login(pending, payload.wechat_code)
        print(f"[edu_login_confirm] got {len(biz_cookies)} cookies", flush=True)
    except EduLoginError as exc:
        print(f"[edu_login_confirm] EduLoginError: {exc}", flush=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        print(f"[edu_login_confirm] unexpected error: {type(exc).__name__}: {exc}", flush=True)
        import traceback
        traceback.print_exc()
        raise

    userid = await fetch_userid(user_id, biz_cookies)
    print(f"[edu_login_confirm] fetched userid={userid}", flush=True)
    await edu_session_store.save_session(user_id, biz_cookies, userid=userid)
    await edu_session_store.delete_pending(user_id)
    return {"logged_in": True, "userid": userid or ""}


@router.get("/schedule_debug")
async def edu_schedule_debug(user: dict | None = Depends(get_optional_user)):
    user_id = _require_user_id(user)
    session = await edu_session_store.load_session(user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Redis 中没有教务登录态")
    cookies = session.get("cookies") or {}
    try:
        result = await query_schedule(cookies)
    except SessionExpiredError as exc:
        raise HTTPException(status_code=409, detail=f"教务登录态不可用：{exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"课表查询失败：{exc}") from exc
    await edu_session_store.save_session(user_id, cookies, userid=session.get("userid"))
    return result


@router.post("/logout")
async def edu_logout(user: dict | None = Depends(get_optional_user)):
    user_id = _require_user_id(user)
    await edu_session_store.delete_pending(user_id)
    await edu_session_store.delete_session(user_id, reason="user_logout")
    return {"status": "ok"}
