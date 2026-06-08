from __future__ import annotations

from datetime import date
from typing import Any

from app.edu.client import SessionExpiredError, post_jwapp

WDKB_REFERER = "https://iedu.jlu.edu.cn/jwapp/sys/wdkb/*default/index.do?EMAP_LANG=zh"


async def get_current_xnxq(biz_cookies: dict[str, str]) -> str | None:
    """当前学年学期代码，例如 "2025-2026-2"。"""
    data = await post_jwapp(
        biz_cookies, "/jwapp/sys/wdkb/modules/jshkcb/dqxnxq.do", referer=WDKB_REFERER
    )
    rows = data.get("datas", {}).get("dqxnxq", {}).get("rows") or []
    if not rows:
        return None
    return rows[0].get("DM")


async def get_current_week(biz_cookies: dict[str, str], xnxq: str) -> int | None:
    parts = xnxq.split("-")
    if len(parts) != 3:
        return None
    xn = f"{parts[0]}-{parts[1]}"
    xq = parts[2]
    today_obj = date.today()
    today = f"{today_obj.year}-{today_obj.month}-{today_obj.day}"
    data = await post_jwapp(
        biz_cookies,
        "/jwapp/sys/wdkb/modules/jshkcb/dqzc.do",
        data={"XN": xn, "XQ": xq, "RQ": today},
        referer=WDKB_REFERER,
    )
    rows = data.get("datas", {}).get("dqzc", {}).get("rows") or []
    if not rows:
        return None
    return rows[0].get("ZC")


async def get_lesson_periods(biz_cookies: dict[str, str]) -> list[dict[str, Any]]:
    """节次时间表：第 N 节 -> 起止时间。"""
    data = await post_jwapp(
        biz_cookies, "/jwapp/sys/wdkb/modules/jshkcb/jc.do", referer=WDKB_REFERER
    )
    rows = data.get("datas", {}).get("jc", {}).get("rows") or []
    return [
        {"index": r.get("DM"), "name": r.get("MC"), "start": r.get("KSSJ"), "end": r.get("JSSJ")}
        for r in rows
    ]


async def query_schedule(biz_cookies: dict[str, str], xnxq: str | None = None) -> dict[str, Any]:
    """查询学生综合学期课表。"""
    if not xnxq:
        xnxq = await get_current_xnxq(biz_cookies)
    if not xnxq:
        raise RuntimeError("无法获取当前学年学期")

    raw = await post_jwapp(
        biz_cookies,
        "/jwapp/sys/wdkb/modules/xskcb/cxxszhxqkb.do",
        data={"XNXQDM": xnxq},
        referer=WDKB_REFERER,
    )
    rows = raw.get("datas", {}).get("cxxszhxqkb", {}).get("rows") or []

    courses: list[dict[str, Any]] = []
    for r in rows:
        courses.append(
            {
                "course": r.get("KCM"),                           # 课程名
                "teacher": r.get("SKJS"),                         # 授课教师
                "weekday": r.get("SKXQ"),                         # 星期几（数字，1=周一）
                "start_period": r.get("KSJC"),                    # 开始节次
                "end_period": r.get("JSJC"),                      # 结束节次
                "period_display": f"{r.get('KSJC_DISPLAY','')}-{r.get('JSJC_DISPLAY','')}",
                "weeks": r.get("SKZC"),                           # 上课周次（位串，如 "111111111111011100000"）
                "weeks_display": r.get("ZCMC"),                   # 周次描述（如 "1-12周,14-16周"）
                "location": r.get("JASMC"),                       # 教室
                "building": r.get("JXLDM_DISPLAY"),               # 教学楼
                "class_name": r.get("BJDM_DISPLAY"),              # 上课班级
                "credit_hours": r.get("XS"),                      # 学时
                "course_type": r.get("KCXZDM_DISPLAY"),           # 课程性质
                "exam_type": r.get("KSLXDM_DISPLAY"),             # 考核方式
            }
        )
    return {
        "xnxq": xnxq,
        "total": len(courses),
        "courses": courses,
    }


__all__ = [
    "SessionExpiredError",
    "query_schedule",
    "get_current_xnxq",
    "get_current_week",
    "get_lesson_periods",
]
