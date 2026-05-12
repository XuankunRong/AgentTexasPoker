from __future__ import annotations

from holdem.providers.base import LLMClient
from holdem.providers.http_utils import post_json


class AnthropicClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.anthropic.com/v1",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def complete(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "max_tokens": 120,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        data = post_json(f"{self.base_url}/messages", payload, headers)
        content = data.get("content", [])
        for part in content:
            text = part.get("text")
            if text:
                return str(text)
        return "{}"
