import httpx

from app.config import settings


class EmbeddingClient:
    def __init__(self) -> None:
        self.api_key = settings.siliconflow_api_key
        self.model = settings.siliconflow_embedding_model
        self.dimensions = settings.embedding_dimensions

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def embed_text(self, text: str) -> list[float]:
        if not self.api_key:
            raise RuntimeError("SILICONFLOW_API_KEY is not configured")

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.siliconflow.cn/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": text,
                    "model": self.model,
                    "dimensions": self.dimensions,
                    "encoding_format": "float",
                },
            )
            response.raise_for_status()

        data = response.json()
        return data["data"][0]["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise RuntimeError("SILICONFLOW_API_KEY is not configured")

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.siliconflow.cn/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": texts,
                    "model": self.model,
                    "dimensions": self.dimensions,
                    "encoding_format": "float",
                },
            )
            response.raise_for_status()

        data = response.json()
        return [item["embedding"] for item in data["data"]]
