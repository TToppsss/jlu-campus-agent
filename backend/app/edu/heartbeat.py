from __future__ import annotations

import asyncio
import time

from app.edu.client import SessionExpiredError, post_jwapp
from app.edu.session import edu_session_store

HEARTBEAT_INTERVAL_SECONDS = 25 * 60
HEARTBEAT_REFERER = "https://iedu.jlu.edu.cn/jwapp/sys/emaphome/portal/index.do"
HEARTBEAT_PATH = "/jwapp/sys/wdkb/modules/jshkcb/dqxnxq.do"


async def _heartbeat_one(app_user_id: str) -> bool:
    data = await edu_session_store.load_session(app_user_id)
    if not data:
        return False
    cookies = data.get("cookies") or {}
    try:
        await post_jwapp(cookies, HEARTBEAT_PATH, referer=HEARTBEAT_REFERER, timeout=15)
    except SessionExpiredError:
        print(f"[edu_heartbeat] SessionExpiredError user_id={app_user_id}; keeping Redis session", flush=True)
        return False
    except Exception:
        return False
    await edu_session_store.update_refreshed_at(app_user_id)
    return True


async def heartbeat_loop() -> None:
    while True:
        try:
            user_ids = await edu_session_store.list_session_user_ids()
            ok = 0
            failed = 0
            for uid in user_ids:
                success = await _heartbeat_one(uid)
                if success:
                    ok += 1
                else:
                    failed += 1
            if user_ids:
                print(
                    f"[edu_heartbeat] 已刷新 {ok}/{len(user_ids)} 教务登录态，失效 {failed} 个",
                    flush=True,
                )
        except Exception as exc:
            print(f"[edu_heartbeat] 异常：{exc}", flush=True)
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
