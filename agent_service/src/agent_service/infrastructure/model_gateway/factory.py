"""Factory for creating configured ModelProviderProtocol instances."""

from __future__ import annotations

from agent_service.config import Settings, settings
from agent_service.domain.protocols import ModelProviderProtocol

from .base_openai import BaseOpenAIAdapter
from .deepseek_provider import DeepSeekProvider
from .fake_provider import FakeModelProvider
from .gemini_provider import GeminiProvider
from .openai_provider import OpenAIProvider


def get_model_provider(
    custom_settings: Settings | None = None,
) -> ModelProviderProtocol:
    """Instantiate and return the configured ModelProviderProtocol adapter.

    Args:
        custom_settings: Optional configuration settings (defaults to app settings).

    Returns:
        Configured ModelProviderProtocol instance.
    """
    cfg = custom_settings or settings
    provider_type = cfg.DEFAULT_MODEL_PROVIDER.lower().strip()

    if provider_type == "openai":
        return OpenAIProvider(
            api_key=cfg.OPENAI_API_KEY,
            default_model=cfg.OPENAI_DEFAULT_MODEL,
            base_url=cfg.OPENAI_BASE_URL,
            timeout_seconds=cfg.MODEL_GATEWAY_TIMEOUT_SECONDS,
            max_retries=cfg.MODEL_GATEWAY_MAX_RETRIES,
        )
    elif provider_type == "gemini":
        return GeminiProvider(
            api_key=cfg.GEMINI_API_KEY,
            default_model=cfg.GEMINI_DEFAULT_MODEL,
            base_url=cfg.GEMINI_BASE_URL,
            timeout_seconds=cfg.MODEL_GATEWAY_TIMEOUT_SECONDS,
            max_retries=cfg.MODEL_GATEWAY_MAX_RETRIES,
        )
    elif provider_type == "deepseek":
        return DeepSeekProvider(
            api_key=cfg.DEEPSEEK_API_KEY,
            default_model=cfg.DEEPSEEK_DEFAULT_MODEL,
            base_url=cfg.DEEPSEEK_BASE_URL,
            timeout_seconds=cfg.MODEL_GATEWAY_TIMEOUT_SECONDS,
            max_retries=cfg.MODEL_GATEWAY_MAX_RETRIES,
        )
    elif provider_type == "openai_compatible":
        return BaseOpenAIAdapter(
            provider_name="openai_compatible",
            default_model=cfg.OPENAI_COMPATIBLE_DEFAULT_MODEL,
            api_key=cfg.OPENAI_COMPATIBLE_API_KEY,
            base_url=cfg.OPENAI_COMPATIBLE_BASE_URL,
            timeout_seconds=cfg.MODEL_GATEWAY_TIMEOUT_SECONDS,
            max_retries=cfg.MODEL_GATEWAY_MAX_RETRIES,
        )
    elif provider_type == "fake":
        return FakeModelProvider()
    else:
        raise ValueError(
            f"Unsupported model provider '{provider_type}'. Supported providers: "
            "'openai', 'gemini', 'deepseek', 'openai_compatible', 'fake'."
        )
