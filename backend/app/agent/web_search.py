from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx


@dataclass
class WebSearchResult:
    title: str
    url: str
    snippet: str = ""


class BingResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[WebSearchResult] = []
        self._in_result = False
        self._in_h2 = False
        self._in_title = False
        self._in_snippet = False
        self._current_url = ""
        self._current_title: list[str] = []
        self._current_snippet: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class") or ""
        if tag == "li" and "b_algo" in class_name:
            self._in_result = True
            self._current_url = ""
            self._current_title = []
            self._current_snippet = []
        elif self._in_result and tag == "h2":
            self._in_h2 = True
        elif self._in_result and self._in_h2 and tag == "a" and not self._current_url:
            href = attrs_dict.get("href") or ""
            if is_public_url(href):
                self._current_url = href
                self._in_title = True
        elif self._in_result and tag == "p":
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title:
            self._in_title = False
        elif tag == "h2" and self._in_h2:
            self._in_h2 = False
        elif tag == "p" and self._in_snippet:
            self._in_snippet = False
        elif tag == "li" and self._in_result:
            title = "".join(self._current_title).strip()
            snippet = "".join(self._current_snippet).strip()
            if title and self._current_url:
                self.results.append(WebSearchResult(title=title, url=self._current_url, snippet=snippet))
            self._in_result = False
            self._in_h2 = False
            self._in_title = False
            self._in_snippet = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._current_title.append(data)
        elif self._in_snippet:
            self._current_snippet.append(data)


def is_public_url(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    host = urlparse(url).netloc.lower()
    return bool(host) and "bing.com" not in host


def normalize_search_query(query: str) -> str:
    value = query.strip()
    for token in ("帮我查一下", "帮我查查", "查一下", "查查", "请问", "是什么", "是多少", "有哪些", "吗", "？", "?"):
        value = value.replace(token, " ")
    value = " ".join(value.split())
    return value or query


async def search_web(query: str, limit: int = 5) -> list[WebSearchResult]:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        response = await client.get(
            "https://cn.bing.com/search",
            params={"q": normalize_search_query(query)},
            headers={"User-Agent": "Mozilla/5.0 JLUCampusAgent/0.1"},
        )
        response.raise_for_status()
    parser = BingResultParser()
    parser.feed(response.text)
    return parser.results[:limit]
