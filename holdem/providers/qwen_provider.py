from __future__ import annotations

from typing import Any

from holdem.providers.base import LLMClient
from holdem.providers.http_utils import post_json


class QwenClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        extra_body: dict[str, Any] | None = None,
        timeout_sec: float = 120.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.extra_body = extra_body or {}
        self.timeout_sec = float(timeout_sec)

    def complete(self, prompt: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.extra_body:
            payload.update(self.extra_body)

        data = post_json(
            f"{self.base_url}/chat/completions",
            payload,
            headers,
            timeout=self.timeout_sec,
        )

        choices = data.get("choices", [])
        if not choices:
            return "{}"

        msg = choices[0].get("message", {})
        content = msg.get("content")
        if isinstance(content, str) and content:
            return content
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if text:
                    return str(text)
        return "{}"
