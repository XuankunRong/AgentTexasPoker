from holdem.providers.anthropic_provider import AnthropicClient
from holdem.providers.base import LLMClient
from holdem.providers.gemini_provider import GeminiClient
from holdem.providers.openai_provider import OpenAIClient
from holdem.providers.qwen_provider import QwenClient


def build_llm_client(
    provider: str,
    model: str,
    api_key: str,
    base_url: str | None = None,
    extra_body: dict | None = None,
    system_prompt: str | None = None,
    timeout_sec: int = 120,
) -> LLMClient:
    p = provider.lower().strip()

    if p == "openai":
        return OpenAIClient(
            api_key=api_key,
            model=model,
            base_url=base_url or "https://api.openai.com/v1",
            extra_body=extra_body,
            system_prompt=system_prompt,
            timeout_sec=timeout_sec,
        )

    if p == "anthropic":
        return AnthropicClient(
            api_key=api_key,
            model=model,
            base_url=base_url or "https://api.anthropic.com/v1",
        )

    if p == "gemini":
        return GeminiClient(
            api_key=api_key,
            model=model,
            base_url=base_url or "https://generativelanguage.googleapis.com/v1beta",
        )

    if p == "qwen":
        return QwenClient(
            api_key=api_key,
            model=model,
            base_url=base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout_sec=timeout_sec,
        )

    raise ValueError(f"Unsupported provider: {provider}")
