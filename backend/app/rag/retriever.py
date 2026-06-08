import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from app.rag.loader import DocumentChunk, LocalDocumentLoader

TOKEN_RE = re.compile(r"[一-鿿]|[a-zA-Z0-9_]+")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


class LexicalRetriever:
    def __init__(self, chunks: list[DocumentChunk]) -> None:
        self.chunks = chunks
        self.chunk_tokens = [Counter(tokenize(chunk.content)) for chunk in chunks]

    def search(self, query: str, limit: int = 4) -> list[DocumentChunk]:
        query_tokens = Counter(tokenize(query))
        if not query_tokens:
            return []

        scored: list[tuple[float, DocumentChunk]] = []
        for chunk, tokens in zip(self.chunks, self.chunk_tokens):
            score = 0.0
            for token, count in query_tokens.items():
                score += min(count, tokens.get(token, 0))
            if query.lower() in chunk.content.lower():
                score += 3
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in scored[:limit]]


@lru_cache
def get_retriever() -> LexicalRetriever:
    project_root = Path(__file__).resolve().parents[3]
    docs_dir = project_root / "data" / "raw_docs"
    chunks = LocalDocumentLoader(docs_dir).load()
    return LexicalRetriever(chunks)
