"""DeepSeek provider implementation using OpenAI-compatible endpoint."""

from __future__ import annotations

from openai import AsyncOpenAI

from .base_openai import BaseOpenAIAdapter


class DeepSeekProvider(BaseOpenAIAdapter):
    """Model provider adapter for DeepSeek models (deepseek-chat, deepseek-reasoner)."""

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com/v1",
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        client: AsyncOpenAI | None = None,
    ) -> None:
        super().__init__(
            provider_name="deepseek",
            default_model=default_model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            client=client,
        )
