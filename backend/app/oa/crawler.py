import re
from datetime import date, timedelta
from urllib.parse import urljoin, urlparse

import httpx
from dateutil.relativedelta import relativedelta

from app.config import settings
from app.db.postgres import NoticeRecord, latest_notices, notices_by_date, upsert_notices_with_ids
from app.rag.vector_retriever import search_oa_notices_by_vector
from app.oa.parser import extract_text

DATE_RE = re.compile(r"(20\d{2})[-年./](\d{1,2})[-月./](\d{1,2})|今天\s*&nbsp;\s*(\d{1,2}:\d{2})|今天\s+(\d{1,2}:\d{2})")
NOTICE_ROW_RE = re.compile(
    r'<A\s+class="font14"\s+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</A>.*?<SPAN\s+class="time"[^>]*>(?P<date>.*?)</SPAN>',
    re.I | re.S,
)
TAG_RE = re.compile(r"<.*?>", re.S)
CAMPUS_NOTICE_CHANNEL_ID = "179577"
NOTICE_LIST_URL = f"https://oa.jlu.edu.cn/defaultroot/PortalInformation!jldxList.action?channelId={CAMPUS_NOTICE_CHANNEL_ID}"


class OaAccessError(RuntimeError):
    pass


def clean_html_text(value: str) -> str:
    value = re.sub(r"<font[^>]*>.*?</font>", "", value, flags=re.I | re.S)
    value = TAG_RE.sub("", value)
    value = value.replace("&nbsp;", " ").replace("\r", " ").replace("\n", " ").strip()
    return re.sub(r"\s+", " ", value)


def parse_date(text: str) -> date | None:
    if "今天" in text:
        return date.today()
    if "昨天" in text:
        return date.today() - timedelta(days=1)
    match = re.search(r"(20\d{2})[-年./](\d{1,2})[-月./](\d{1,2})", text)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def is_same_site(url: str) -> bool:
    base = urlparse(settings.oa_base_url)
    parsed = urlparse(url)
    return parsed.netloc == base.netloc or parsed.netloc == ""


async def fetch_html(client: httpx.AsyncClient, url: str) -> str:
    try:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        raise OaAccessError("无法连接吉林大学电子校务平台。请确认当前设备已连接校园网或已开启学校 VPN 后再试。") from exc
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type and content_type:
        return ""
    return response.text


def extract_notice_rows(html: str, page_url: str) -> list[NoticeRecord]:
    records: list[NoticeRecord] = []
    for match in NOTICE_ROW_RE.finditer(html):
        title = clean_html_text(match.group("title"))
        href = urljoin(page_url, match.group("href"))
        date_text = clean_html_text(match.group("date"))
        if not title or not is_same_site(href):
            continue
        records.append(
            NoticeRecord(
                title=title,
                url=href,
                publish_date=parse_date(date_text),
                content="",
            )
        )
    return records


async def enrich_notice_detail(client: httpx.AsyncClient, record: NoticeRecord) -> NoticeRecord:
    try:
        html = await fetch_html(client, record.url)
    except (OaAccessError, httpx.HTTPError):
        return record
    if html:
        text = extract_text(html)
        record.content = text[:12000]
        record.publish_date = record.publish_date or parse_date(text)
    return record


async def crawl_oa_public_notices(max_pages: int | None = None, cutoff_days: int | None = None) -> list[NoticeRecord]:
    max_pages = max_pages or settings.oa_crawl_max_pages
    if cutoff_days is not None:
        cutoff = date.today() - timedelta(days=cutoff_days)
    else:
        cutoff = date.today() - relativedelta(months=settings.oa_crawl_months)
    records: list[NoticeRecord] = []
    seen_urls: set[str] = set()

    async with httpx.AsyncClient(
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0 JLUCampusAgent/0.1"},
    ) as client:
        for page in range(1, max_pages + 1):
            page_url = NOTICE_LIST_URL if page == 1 else f"{NOTICE_LIST_URL}&startPage={page}"
            try:
                html = await fetch_html(client, page_url)
            except (OaAccessError, httpx.HTTPError) as e:
                print(f"第 {page} 页失败：{e}", flush=True)
                continue
            page_records = extract_notice_rows(html, page_url)
            if not page_records and page == 1:
                raise OaAccessError("已访问吉林大学电子校务平台，但没有解析到校园通知列表。请确认已连接校园网，或 OA 页面结构是否发生变化。")
            page_has_new = False
            for record in page_records:
                if record.publish_date and record.publish_date < cutoff:
                    continue
                page_has_new = True
                if record.url in seen_urls:
                    continue
                seen_urls.add(record.url)
                records.append(await enrich_notice_detail(client, record))
            if not page_has_new and page > 1:
                return records
    return records


async def refresh_oa_notices(cutoff_days: int | None = None, max_pages: int | None = None) -> dict[str, int | str | list[int]]:
    try:
        records = await crawl_oa_public_notices(max_pages=max_pages, cutoff_days=cutoff_days)
    except OaAccessError as exc:
        return {"fetched": 0, "changed": 0, "changed_ids": [], "error": str(exc)}
    except httpx.HTTPError as exc:
        return {"fetched": 0, "changed": 0, "changed_ids": [], "error": f"访问吉林大学电子校务平台失败：{exc}。请确认已连接校园网或学校 VPN。"}
    changed_ids = upsert_notices_with_ids(records)
    return {"fetched": len(records), "changed": len(changed_ids), "changed_ids": changed_ids, "error": ""}


async def search_oa_notices(query: str, limit: int = 8) -> tuple[dict[str, int | str | bool], list[dict]]:
    refresh_result: dict[str, int | str | bool] = {"fetched": 0, "changed": 0, "error": "", "refreshed": False}

    # 优先向量检索
    vector_results = await search_oa_notices_by_vector(query, limit=limit)
    if vector_results:
        # 从 metadata 里提取完整通知信息
        results = []
        seen_ids = set()
        for item in vector_results:
            metadata = item["metadata"]
            notice_id = metadata.get("notice_id")
            if notice_id and notice_id not in seen_ids:
                seen_ids.add(notice_id)
                results.append({
                    "title": metadata.get("title"),
                    "url": metadata.get("url"),
                    "publish_date": metadata.get("publish_date"),
                    "content": item["chunk_text"],
                })
                if len(results) >= limit:
                    break
        if results:
            return refresh_result, results

    # 向量检索无结果，fallback 到日期查询
    if "今天" in query:
        results = notices_by_date(date.today(), limit=limit)
    elif "昨天" in query:
        results = notices_by_date(date.today() - timedelta(days=1), limit=limit)
    elif any(k in query for k in ("最新", "新通知", "新公告", "发布")):
        results = latest_notices(limit=limit)
    else:
        results = []

    return refresh_result, results
