from pathlib import Path
from pydantic import BaseModel


class DocumentChunk(BaseModel):
    source: str
    content: str


class LocalDocumentLoader:
    def __init__(self, docs_dir: Path) -> None:
        self.docs_dir = docs_dir

    def load(self) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        if not self.docs_dir.exists():
            return chunks

        for path in sorted(self.docs_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                continue
            chunks.extend(split_text(text, source=path.name))

        for path in sorted(self.docs_dir.glob("*.txt")):
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                continue
            chunks.extend(split_text(text, source=path.name))

        return chunks


def split_text(text: str, source: str, chunk_size: int = 500, overlap: int = 80) -> list[DocumentChunk]:
    paragraphs = [item.strip() for item in text.split("\n\n") if item.strip()]
    chunks: list[DocumentChunk] = []
    current = ""

    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= chunk_size:
            current = f"{current}\n\n{paragraph}".strip()
            continue

        if current:
            chunks.append(DocumentChunk(source=source, content=current))
        current = paragraph

    if current:
        chunks.append(DocumentChunk(source=source, content=current))

    expanded: list[DocumentChunk] = []
    for chunk in chunks:
        if len(chunk.content) <= chunk_size:
            expanded.append(chunk)
            continue
        start = 0
        while start < len(chunk.content):
            end = start + chunk_size
            expanded.append(DocumentChunk(source=source, content=chunk.content[start:end]))
            start = max(end - overlap, end)

    return expanded
