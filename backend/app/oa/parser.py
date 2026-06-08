from html.parser import HTMLParser
from urllib.parse import urljoin


class LinkExtractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self._href = urljoin(self.base_url, href)
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text_parts.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            text = "".join(self._text_parts).strip()
            if text:
                self.links.append((text, self._href))
            self._href = None
            self._text_parts = []


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = False
        self._in_content = False
        self._in_time = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._skip = True
        # 检测时间容器
        if tag.lower() == "div":
            for attr, value in attrs:
                if attr == "class" and value:
                    if "content_time" in value:
                        self._in_time = True
                    elif "content_font" in value:
                        self._in_content = True
                    break

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._skip = False
        if tag.lower() == "div":
            if self._in_time:
                self._in_time = False
                self.parts.append("\n\n")  # 时间后空两行
            elif self._in_content:
                self._in_content = False
        if self._in_content and tag.lower() in {"p", "div", "br", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip and (self._in_time or self._in_content):
            text = data.strip()
            if text:
                self.parts.append(text)

    def text(self) -> str:
        lines = [line.strip() for line in "".join(self.parts).splitlines() if line.strip()]
        return "\n".join(lines)


def extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    parser = LinkExtractor(base_url)
    parser.feed(html)
    return parser.links


def extract_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return parser.text()
