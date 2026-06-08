from enum import StrEnum


class Intent(StrEnum):
    OA_NOTICE_QUERY = "oa_notice_query"
    CAMPUS_QA = "campus_qa"
    DIRECT_CHAT = "direct_chat"


CAMPUS_QA_KEYWORDS = ["校园卡", "缓考", "奖学金", "大创", "创新创业", "教务", "申请", "流程", "材料", "图书馆"]
OA_QUERY_KEYWORDS = ["oa", "电子校务", "校务平台", "今天", "最新", "新通知", "新公告", "发布了什么", "查查"]


def detect_intent(message: str) -> Intent:
    compact = message.strip()

    if any(keyword in compact.lower() for keyword in ("oa",)) or any(keyword in compact for keyword in OA_QUERY_KEYWORDS):
        if any(keyword in compact for keyword in ("通知", "公告", "发布", "最新", "今天", "查查", "整理")):
            return Intent.OA_NOTICE_QUERY

    if any(keyword in compact for keyword in CAMPUS_QA_KEYWORDS):
        return Intent.CAMPUS_QA

    return Intent.DIRECT_CHAT
