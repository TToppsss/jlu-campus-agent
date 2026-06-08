from __future__ import annotations

from typing import Any

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)


class SessionExpiredError(RuntimeError):
    """业务请求时检测到登录态已失效。"""


def _build_cookie_jar(biz_cookies: dict[str, str]) -> httpx.Cookies:
    jar = httpx.Cookies()
    for k, v in biz_cookies.items():
        jar.set(k, v, domain="iedu.jlu.edu.cn", path="/")
    return jar


def _is_session_expired(resp: httpx.Response) -> bool:
    """常见失效特征：跳转到 CAS / 401 / HTML 中包含登录提示。"""
    if resp.status_code == 401:
        return True
    if 300 <= resp.status_code < 400:
        loc = (resp.headers.get("location") or "").lower()
        if "cas.jlu.edu.cn" in loc or "/login" in loc:
            return True
    ctype = (resp.headers.get("content-type") or "").lower()
    if "text/html" in ctype:
        body = resp.text[:1500]
        if "cas.jlu.edu.cn" in body and ("login" in body.lower() or "登录" in body):
            return True
    return False


def _sync_cookies(client: httpx.AsyncClient, biz_cookies: dict[str, str]) -> None:
    for name, value in client.cookies.items():
        biz_cookies[name] = value


def _deduplicate_cookies(client: httpx.AsyncClient) -> None:
    """去重 cookie jar，每个 name 只保留最后一个值。"""
    jar_dict: dict[str, str] = {}
    for cookie in client.cookies.jar:
        jar_dict[cookie.name] = cookie.value
    client.cookies.jar.clear()
    for name, value in jar_dict.items():
        client.cookies.set(name, value)


async def _warmup_wdkb(client: httpx.AsyncClient, biz_cookies: dict[str, str]) -> None:
    """访问课表子应用入口，服务端可能会刷新 cookie。"""
    old_weu = biz_cookies.get('_WEU', '')[:50]
    resp = await client.get("https://iedu.jlu.edu.cn/jwapp/sys/wdkb/*default/index.do?EMAP_LANG=zh")
    print(f"[warmup_wdkb] status={resp.status_code} cookies_before_dedup={len(list(client.cookies.jar))}", flush=True)
    _deduplicate_cookies(client)
    print(f"[warmup_wdkb] cookies_after_dedup={len(list(client.cookies.jar))}", flush=True)
    _sync_cookies(client, biz_cookies)
    new_weu = biz_cookies.get('_WEU', '')[:50]
    print(f"[warmup_wdkb] synced cookies, biz_cookies now has {len(biz_cookies)} keys", flush=True)
    print(f"[warmup_wdkb] _WEU changed: {old_weu != new_weu}, old={old_weu}, new={new_weu}", flush=True)


async def post_jwapp(
    biz_cookies: dict[str, str],
    path: str,
    data: dict[str, Any] | None = None,
    referer: str = "https://iedu.jlu.edu.cn/jwapp/sys/emaphome/portal/index.do",
    timeout: int = 20,
) -> Any:
    """对 iedu.jlu.edu.cn/jwapp 下任意接口的 POST 调用，返回解析后的 JSON。"""
    url = f"https://iedu.jlu.edu.cn{path}" if path.startswith("/") else path
    headers = {
        "User-Agent": USER_AGENT,
        "Origin": "https://iedu.jlu.edu.cn",
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    async with httpx.AsyncClient(
        cookies=_build_cookie_jar(biz_cookies), headers=headers, timeout=timeout, follow_redirects=False
    ) as client:
        resp = await client.post(url, data=data or {})
        if resp.status_code == 403:
            print(f"[post_jwapp] got 403, warmup and retry. path={path}", flush=True)
            await _warmup_wdkb(client, biz_cookies)
            # warmup 后 biz_cookies 已更新，需要重新构建 client 的 cookie jar
            for name, value in biz_cookies.items():
                client.cookies.set(name, value)
            resp = await client.post(url, data=data or {})
            print(f"[post_jwapp] retry status={resp.status_code}", flush=True)
        _sync_cookies(client, biz_cookies)
    if _is_session_expired(resp):
        raise SessionExpiredError("教务登录态已失效")
    if resp.status_code == 403:
        raise RuntimeError(f"教务接口拒绝访问 status=403 path={path}")
    resp.raise_for_status()
    try:
        return resp.json()
    except Exception as exc:
        raise RuntimeError(f"教务接口返回非 JSON：{resp.text[:200]}") from exc


async def get_jwapp(
    biz_cookies: dict[str, str],
    path: str,
    params: dict[str, Any] | None = None,
    referer: str = "https://iedu.jlu.edu.cn/jwapp/sys/emaphome/portal/index.do",
    timeout: int = 20,
) -> httpx.Response:
    url = f"https://iedu.jlu.edu.cn{path}" if path.startswith("/") else path
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": referer,
    }
    async with httpx.AsyncClient(
        cookies=_build_cookie_jar(biz_cookies), headers=headers, timeout=timeout, follow_redirects=False
    ) as client:
        resp = await client.get(url, params=params or {})
        if resp.status_code == 403:
            await _warmup_wdkb(client, biz_cookies)
            # warmup 后 biz_cookies 已更新，需要重新构建 client 的 cookie jar
            for name, value in biz_cookies.items():
                client.cookies.set(name, value)
            resp = await client.get(url, params=params or {})
        _sync_cookies(client, biz_cookies)
    if _is_session_expired(resp):
        raise SessionExpiredError("教务登录态已失效")
    return resp
