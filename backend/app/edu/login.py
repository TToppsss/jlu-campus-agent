from __future__ import annotations

import base64
import re
import time
from typing import Any
from urllib.parse import quote

import httpx

from app.edu.des import str_enc

CAS_BASE = "https://cas.jlu.edu.cn"
SERVICE_URL = "https://iedu.jlu.edu.cn/jwapp/sys/emaphome/portal/index.do"
LOGIN_URL = f"{CAS_BASE}/tpass/login?service={quote(SERVICE_URL, safe='')}"
CAPTCHA_URL = f"{CAS_BASE}/tpass/code"
RECHECK_URL = f"{CAS_BASE}/tpass/recheckcode"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}

LT_RE = re.compile(r'name="lt"\s+value="([^"]+)"')
EXECUTION_RE = re.compile(r'name="execution"\s+value="([^"]+)"')
_ERROR_HINT_RE = re.compile(r'<span[^>]*id="msg"[^>]*>(.*?)</span>', re.S)


class EduLoginError(RuntimeError):
    pass


def _parse_login_form(html: str) -> tuple[str, str]:
    lt = LT_RE.search(html)
    execution = EXECUTION_RE.search(html)
    if not lt or not execution:
        raise EduLoginError("解析 CAS 登录表单失败，可能页面结构发生变化")
    return lt.group(1), execution.group(1)


def _extract_error(html: str) -> str | None:
    m = _ERROR_HINT_RE.search(html)
    if m:
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip()
        if text:
            return text
    return None


def _cookies_to_dict(cookie_jar: httpx.Cookies) -> dict[str, str]:
    return {name: value for name, value in cookie_jar.items()}


def _restore_cookies(cookies: dict[str, str]) -> httpx.Cookies:
    jar = httpx.Cookies()
    for k, v in cookies.items():
        jar.set(k, v, domain="cas.jlu.edu.cn", path="/")
    return jar


async def init_login(username: str, password: str) -> dict[str, Any]:
    """步骤一：拿登录页 → POST 账号密码 → 取图形码图片返回前端。"""
    cookie_jar = httpx.Cookies()
    async with httpx.AsyncClient(
        cookies=cookie_jar, headers=HEADERS, timeout=20, follow_redirects=False
    ) as client:
        try:
            resp = await client.get(LOGIN_URL)
        except httpx.HTTPError as exc:
            raise EduLoginError(f"无法访问吉大 CAS：{exc}。请确认已连接校园网或 VPN。") from exc
        if resp.status_code != 200:
            raise EduLoginError(f"获取 CAS 登录页失败 status={resp.status_code}")
        lt, execution = _parse_login_form(resp.text)

        rsa = str_enc(username + password + lt, "1", "2", "3")
        e1s_form = {
            "rsa": rsa,
            "ul": str(len(username)),
            "pl": str(len(password)),
            "sl": "0",
            "lt": lt,
            "execution": execution,
            "_eventId": "submit",
        }
        try:
            resp = await client.post(LOGIN_URL, data=e1s_form, headers={"Referer": LOGIN_URL})
        except httpx.HTTPError as exc:
            raise EduLoginError(f"提交账号密码失败：{exc}") from exc
        if resp.status_code not in (200, 302):
            raise EduLoginError(f"提交账号密码失败 status={resp.status_code}")
        try:
            new_lt, new_execution = _parse_login_form(resp.text)
        except EduLoginError:
            error_msg = _extract_error(resp.text)
            raise EduLoginError(error_msg or "账号或密码错误，请检查后重试") from None

        try:
            captcha_resp = await client.get(CAPTCHA_URL, headers={"Referer": LOGIN_URL})
        except httpx.HTTPError as exc:
            raise EduLoginError(f"获取图形验证码失败：{exc}") from exc
        if captcha_resp.status_code != 200 or not captcha_resp.content:
            raise EduLoginError(f"获取图形验证码失败 status={captcha_resp.status_code}")

        captcha_b64 = base64.b64encode(captcha_resp.content).decode("ascii")
        ctype = captcha_resp.headers.get("content-type", "image/jpeg")

        pending = {
            "lt": new_lt,
            "execution": new_execution,
            "cas_cookies": _cookies_to_dict(client.cookies),
            "username": username,
            "expires_at": int(time.time()) + 280,
        }
        return {
            "pending": pending,
            "captcha_image": f"data:{ctype};base64,{captcha_b64}",
        }


async def refresh_captcha(pending: dict[str, Any]) -> dict[str, Any]:
    """重新取一张图形码（lt 不变，只换图）。"""
    cookie_jar = _restore_cookies(pending.get("cas_cookies") or {})
    async with httpx.AsyncClient(
        cookies=cookie_jar, headers=HEADERS, timeout=20, follow_redirects=False
    ) as client:
        try:
            captcha_resp = await client.get(CAPTCHA_URL, headers={"Referer": LOGIN_URL})
        except httpx.HTTPError as exc:
            raise EduLoginError(f"刷新图形验证码失败：{exc}") from exc
        if captcha_resp.status_code != 200 or not captcha_resp.content:
            raise EduLoginError(f"刷新图形验证码失败 status={captcha_resp.status_code}")
        b64 = base64.b64encode(captcha_resp.content).decode("ascii")
        ctype = captcha_resp.headers.get("content-type", "image/jpeg")
        pending["cas_cookies"] = _cookies_to_dict(client.cookies)
        return {
            "pending": pending,
            "captcha_image": f"data:{ctype};base64,{b64}",
        }


async def send_wechat_code(pending: dict[str, Any], captcha_text: str) -> dict[str, Any]:
    """步骤二：拿用户输入的图形码 → GET recheckcode 触发微信下发。"""
    if not captcha_text or not captcha_text.strip():
        raise EduLoginError("请输入图形验证码")
    captcha_text = captcha_text.strip()

    cookie_jar = _restore_cookies(pending.get("cas_cookies") or {})
    async with httpx.AsyncClient(
        cookies=cookie_jar, headers=HEADERS, timeout=20, follow_redirects=False
    ) as client:
        t_ms = int(time.time() * 1000)
        try:
            recheck = await client.get(
                RECHECK_URL,
                params={"code": captcha_text, "t": str(t_ms)},
                headers={"Referer": LOGIN_URL},
            )
        except httpx.HTTPError as exc:
            raise EduLoginError(f"触发微信验证码失败：{exc}") from exc
        mobile_info = (
            recheck.cookies.get("recheck_mobile_error_info")
            or client.cookies.get("recheck_mobile_error_info")
        )
        if mobile_info != "success":
            raise EduLoginError("图形验证码错误，请重新输入或刷新图形码")

        pending["captcha_code"] = captcha_text
        pending["cas_cookies"] = _cookies_to_dict(client.cookies)
        return {"pending": pending}


async def confirm_login(pending: dict[str, Any], wechat_code: str) -> dict[str, str]:
    """步骤三：用户填了微信码 → 提交图形码+微信码 → 拿 ticket → 兑换业务 cookies。"""
    if not wechat_code or not wechat_code.strip():
        raise EduLoginError("请输入微信验证码")
    if not pending.get("captcha_code"):
        raise EduLoginError("尚未通过图形验证码校验，请先发送微信验证码")
    wechat_code = wechat_code.strip()

    cookie_jar = _restore_cookies(pending.get("cas_cookies") or {})
    async with httpx.AsyncClient(
        cookies=cookie_jar, headers=HEADERS, timeout=20, follow_redirects=False
    ) as client:
        # 根据 HAR: code=图形码&WxCode=微信码&rsa=&ul=&pl=&sl=&lt=...&execution=...&_eventId=submit
        final_form = {
            "code": pending["captcha_code"],
            "WxCode": wechat_code,
            "rsa": "",
            "ul": "",
            "pl": "",
            "sl": "",
            "lt": pending["lt"],
            "execution": pending["execution"],
            "_eventId": "submit",
        }
        try:
            resp = await client.post(LOGIN_URL, data=final_form, headers={"Referer": LOGIN_URL})
        except httpx.HTTPError as exc:
            raise EduLoginError(f"提交微信验证码失败：{exc}") from exc
        if resp.status_code != 302:
            error_msg = _extract_error(resp.text)
            raise EduLoginError(error_msg or "微信验证码错误或已过期，请重试")
        ticket_url = resp.headers.get("Location") or ""
        if "ticket=" not in ticket_url:
            raise EduLoginError("未拿到 CAS ticket，登录失败")

        biz_jar = httpx.Cookies()
        async with httpx.AsyncClient(
            cookies=biz_jar, headers=HEADERS, timeout=20, follow_redirects=True
        ) as biz:
            biz_resp = await biz.get(ticket_url)
            if biz_resp.status_code not in (200, 302):
                raise EduLoginError(f"兑换业务 cookies 失败 status={biz_resp.status_code}")
            biz_cookies = _cookies_to_dict(biz.cookies)
        if "route" not in biz_cookies and "GS_SESSIONID" not in biz_cookies:
            raise EduLoginError("登录成功但未获取到业务 cookies")
        return biz_cookies


async def fetch_userid(app_user_id: str, biz_cookies: dict[str, str]) -> str | None:
    cookie_jar = httpx.Cookies()
    for k, v in biz_cookies.items():
        cookie_jar.set(k, v, domain="iedu.jlu.edu.cn", path="/")
    async with httpx.AsyncClient(
        cookies=cookie_jar, headers=HEADERS, timeout=20, follow_redirects=True
    ) as client:
        try:
            resp = await client.get(
                "https://iedu.jlu.edu.cn/jwapp/sys/wdkb/*default/index.do?EMAP_LANG=zh"
            )
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        # 访问 wdkb 后服务端可能下发新 cookie，去重后写回 biz_cookies
        jar_dict: dict[str, str] = {}
        for cookie in client.cookies.jar:
            jar_dict[cookie.name] = cookie.value
        biz_cookies.clear()
        biz_cookies.update(jar_dict)
        match = re.search(r'"userid"\s*:\s*"(\d+)"', resp.text)
        return match.group(1) if match else None
