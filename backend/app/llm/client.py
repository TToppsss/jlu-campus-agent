from typing import Any

import httpx

from app.config import settings


class DeepSeekClient:
    def __init__(self) -> None:
        self.base_url = settings.deepseek_base_url.rstrip("/")
        self.api_key = settings.deepseek_api_key
        self.model = settings.deepseek_model

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def chat_json(self, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
        return await self._chat(messages=messages, temperature=temperature, json_mode=True)

    async def chat_text(self, messages: list[dict[str, str]], temperature: float = 0.3) -> str:
        return await self._chat(messages=messages, temperature=temperature, json_mode=False)

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "tools": tools,
            "tool_choice": "auto",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]

    async def _chat(self, messages: list[dict[str, str]], temperature: float, json_mode: bool) -> str:
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]["content"]
