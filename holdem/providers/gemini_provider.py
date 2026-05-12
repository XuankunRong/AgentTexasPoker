from __future__ import annotations

from urllib.parse import quote_plus

from holdem.providers.base import LLMClient
from holdem.providers.http_utils import post_json


class GeminiClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def complete(self, prompt: str) -> str:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        url = (
            f"{self.base_url}/models/{quote_plus(self.model)}:generateContent"
            f"?key={quote_plus(self.api_key)}"
        )
        data = post_json(url, payload, headers={})
        candidates = data.get("candidates", [])
        for cand in candidates:
            parts = cand.get("content", {}).get("parts", [])
            for part in parts:
                text = part.get("text")
                if text:
                    return str(text)
        return "{}"
