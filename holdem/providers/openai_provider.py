from __future__ import annotations

from typing import Any

from holdem.providers.base import LLMClient
from holdem.providers.http_utils import post_json


class OpenAIClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        extra_body: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        timeout_sec: float = 120.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.extra_body = extra_body or {}
        self.system_prompt = (system_prompt or "").strip()
        self.timeout_sec = float(timeout_sec)

    def complete(self, prompt: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        messages: list[dict[str, str]] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt})
        chat_payload = {
            "model": self.model,
            "messages": messages,
        }
        if self.extra_body:
            chat_payload.update(self.extra_body)
        try:
            data = post_json(
                f"{self.base_url}/chat/completions",
                chat_payload,
                headers,
                timeout=self.timeout_sec,
            )
            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content")
                if isinstance(content, str) and content:
                    return content
                if isinstance(content, list):
                    for part in content:
                        text = part.get("text") if isinstance(part, dict) else None
                        if text:
                            return str(text)
        except Exception:
            pass

        # Fallback for servers that implement /responses only.
        responses_payload = {"model": self.model, "input": prompt}
        if self.extra_body:
            responses_payload.update(self.extra_body)
        data = post_json(
            f"{self.base_url}/responses",
            responses_payload,
            headers,
            timeout=self.timeout_sec,
        )
        if "output_text" in data and data["output_text"]:
            return str(data["output_text"])
        output = data.get("output", [])
        for item in output:
            for content in item.get("content", []):
                text = content.get("text")
                if text:
                    return str(text)
        return "{}"
