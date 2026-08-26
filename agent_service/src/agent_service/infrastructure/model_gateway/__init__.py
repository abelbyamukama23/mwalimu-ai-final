"""Model Gateway package exposing provider adapters, factory, and error hierarchy."""

from .base_openai import BaseOpenAIAdapter
from .deepseek_provider import DeepSeekProvider
from .errors import (
    ModelAuthenticationError,
    ModelInvalidRequestError,
    ModelProviderError,
    ModelRateLimitError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from .factory import get_model_provider
from .fake_provider import FakeModelProvider
from .gemini_provider import GeminiProvider
from .openai_provider import OpenAIProvider

__all__ = [
    "BaseOpenAIAdapter",
    "DeepSeekProvider",
    "FakeModelProvider",
    "GeminiProvider",
    "ModelAuthenticationError",
    "ModelInvalidRequestError",
    "ModelProviderError",
    "ModelRateLimitError",
    "ModelTimeoutError",
    "ModelUnavailableError",
    "OpenAIProvider",
    "get_model_provider",
]
