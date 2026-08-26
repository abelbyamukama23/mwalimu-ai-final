"""OpenAI provider implementation of ModelProviderProtocol."""

from __future__ import annotations

from openai import AsyncOpenAI

from .base_openai import BaseOpenAIAdapter


class OpenAIProvider(BaseOpenAIAdapter):
    """Model provider adapter for OpenAI models (GPT-4o, GPT-4o-mini)."""

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "gpt-4o",
        base_url: str | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        client: AsyncOpenAI | None = None,
    ) -> None:
        super().__init__(
            provider_name="openai",
            default_model=default_model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            client=client,
        )
