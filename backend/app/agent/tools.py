from app.llm.client import DeepSeekClient
from app.oa.crawler import search_oa_notices
from app.rag.loader import DocumentChunk

CAMPUS_QA_SYSTEM_PROMPT = """
你是吉林大学校园问答助手。请根据给定资料回答用户问题。

要求：
1. 优先依据资料回答，不要编造政策细节。
2. 如果资料不足，明确说"当前资料不足以确认"，并建议用户查看学院或学校官方通知。
3. 回答要面向学生，简洁、可执行。
4. 涉及截止时间、材料、流程时，用清单表达。
""".strip()

OA_NOTICE_SYSTEM_PROMPT = """
你是吉林大学校园通知整理助手。用户在查询吉林大学电子校务平台 OA 的公开通知。

要求：
1. 只根据给定通知列表和正文摘要回答。
2. 优先整理对学生有用的信息：报名、申报、竞赛、奖学金、讲座、项目、截止时间。
3. 每条通知尽量给出：标题、日期、重点、下一步、链接。
4. 不要编造未提供的日期、要求或链接。
""".strip()


def format_context(chunks: list[DocumentChunk]) -> str:
    if not chunks:
        return "无可用资料。"
    return "\n\n".join(
        f"资料{index + 1}（来源：{chunk.source}）：\n{chunk.content}"
        for index, chunk in enumerate(chunks)
    )


async def answer_campus_question(message: str, chunks: list[DocumentChunk]) -> str:
    client = DeepSeekClient()
    if not client.is_configured:
        if not chunks:
            return "当前没有配置 DeepSeek API Key，也没有检索到可用资料。"
        sources = "\n".join(f"- {chunk.source}: {chunk.content[:120]}" for chunk in chunks)
        return f"当前没有配置 DeepSeek API Key，我先根据检索资料给你参考：\n{sources}"

    return await client.chat_text(
        messages=[
            {"role": "system", "content": CAMPUS_QA_SYSTEM_PROMPT},
            {"role": "user", "content": f"用户问题：{message}\n\n可用资料：\n{format_context(chunks)}"},
        ]
    )


async def answer_oa_notice_query(message: str) -> tuple[str, list[dict]]:
    refresh_result, notices = await search_oa_notices(message)
    if not notices:
        error = refresh_result.get("error")
        if error:
            return f"我尝试连接吉林大学电子校务平台更新通知，但当前访问失败：{error}\n本地数据库中也没有检索到相关通知。", []
        return "我已经检查本地 OA 通知数据库，但没有找到相关通知。", []

    notice_context = "\n\n".join(
        f"通知{index + 1}\n标题：{item.get('title') or ''}\n日期：{item.get('publish_date') or '未知'}\n链接：{item.get('url') or ''}\n正文摘要：{(item.get('content') or '')[:1000]}"
        for index, item in enumerate(notices)
    )
    refresh_note = "以下结果来自本地 OA 通知数据库；后台会每 15 分钟自动更新一次。"

    client = DeepSeekClient()
    if not client.is_configured:
        simple = "\n".join(
            f"- {item.get('publish_date') or '日期未知'} {item.get('title')} {item.get('url')}"
            for item in notices
        )
        return f"{refresh_note}\n{simple}", notices

    answer = await client.chat_text(
        messages=[
            {"role": "system", "content": OA_NOTICE_SYSTEM_PROMPT},
            {"role": "user", "content": f"用户问题：{message}\n{refresh_note}\n\n通知资料：\n{notice_context}"},
        ]
    )
    return answer, notices
