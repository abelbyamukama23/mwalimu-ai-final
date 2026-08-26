"""Normalized domain exception hierarchy for model provider operations."""

from __future__ import annotations


class ModelProviderError(Exception):
    """Base exception for all model provider errors.

    Translates vendor-specific SDK errors into standard domain exceptions so
    that the application layer remains decoupled from provider specifics.
    """

    def __init__(
        self,
        message: str,
        provider: str = "",
        raw_error: Exception | None = None,
    ) -> None:
        self.provider = provider
        self.raw_error = raw_error
        super().__init__(message)


class ModelAuthenticationError(ModelProviderError):
    """Raised when provider credentials or API keys are missing or rejected."""


class ModelRateLimitError(ModelProviderError):
    """Raised when provider rate limits or quotas are exceeded (transient error)."""


class ModelTimeoutError(ModelProviderError):
    """Raised when a model request times out."""


class ModelUnavailableError(ModelProviderError):
    """Raised when the provider service is temporarily unavailable or returning 5xx."""


class ModelInvalidRequestError(ModelProviderError):
    """Raised when a request is malformed or parameters are invalid."""
