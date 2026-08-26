"""Google Gemini provider implementation using OpenAI-compatible endpoint."""

from __future__ import annotations

from openai import AsyncOpenAI

from .base_openai import BaseOpenAIAdapter


class GeminiProvider(BaseOpenAIAdapter):
    """Model provider adapter for Google Gemini models.

    Supports gemini-2.0-flash and gemini-1.5-pro via Google's official
    OpenAI-compatible endpoint.
    """

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "gemini-2.0-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/",
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        client: AsyncOpenAI | None = None,
    ) -> None:
        super().__init__(
            provider_name="gemini",
            default_model=default_model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            client=client,
        )
