"""Application settings and Model Gateway configuration for the Agent Service."""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General Service
    ENVIRONMENT: str = Field(default="development")
    LOG_LEVEL: str = Field(default="INFO")

    # Model Gateway Provider Selection
    DEFAULT_MODEL_PROVIDER: str = Field(
        default="openai",
        description=(
            "Active provider: 'openai', 'gemini', 'deepseek', "
            "'openai_compatible', 'fake'"
        ),
    )

    # OpenAI Configuration
    OPENAI_API_KEY: str | None = Field(default=None)
    OPENAI_DEFAULT_MODEL: str = Field(default="gpt-4o")
    OPENAI_BASE_URL: str | None = Field(default=None)

    # Gemini Configuration (uses Google's OpenAI-compatible endpoint)
    GEMINI_API_KEY: str | None = Field(default=None)
    GEMINI_DEFAULT_MODEL: str = Field(default="gemini-2.0-flash")
    GEMINI_BASE_URL: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/"
    )

    # DeepSeek Configuration
    DEEPSEEK_API_KEY: str | None = Field(default=None)
    DEEPSEEK_DEFAULT_MODEL: str = Field(default="deepseek-chat")
    DEEPSEEK_BASE_URL: str = Field(default="https://api.deepseek.com/v1")

    # Generic OpenAI-Compatible Endpoint Configuration
    OPENAI_COMPATIBLE_API_KEY: str | None = Field(default=None)
    OPENAI_COMPATIBLE_DEFAULT_MODEL: str = Field(default="default-model")
    OPENAI_COMPATIBLE_BASE_URL: str = Field(default="http://localhost:8000/v1")

    # Gateway Execution Limits
    MODEL_GATEWAY_TIMEOUT_SECONDS: float = Field(default=60.0)
    MODEL_GATEWAY_MAX_RETRIES: int = Field(default=2)

    # Platform API & Knowledge Gateway Configuration
    PLATFORM_API_BASE_URL: str = Field(default="http://localhost:8000")
    KNOWLEDGE_GATEWAY_TIMEOUT_SECONDS: float = Field(default=15.0)

    # Authentication & Security
    JWT_SECRET_KEY: str = Field(
        default="mwalimu-insecure-dev-secret-key-change-in-production"
    )
    JWT_ALGORITHM: str = Field(default="HS256")

    # Platform Completion Callback Configuration (Domain D)
    PLATFORM_COMPLETION_URL: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PLATFORM_COMPLETION_URL", "AGENT_SERVICE_PLATFORM_COMPLETION_URL"
        ),
        description="Base URL for Platform API internal completion callbacks.",
    )
    INTERNAL_SERVICE_SECRET_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "INTERNAL_SERVICE_SECRET_KEY", "AGENT_SERVICE_PLATFORM_COMPLETION_SECRET"
        ),
        description="Shared secret key for signing Domain D completion callback JWTs.",
    )

    # Domain S — Agent Stream Capability Token Verification
    AGENT_STREAM_JWT_SECRET_KEY: str | None = Field(
        default=None,
        description=(
            "Signing key for Domain S stream capability tokens. "
            "Must be configured separately from JWT_SECRET_KEY (Domain B). "
            "Falls back to JWT_SECRET_KEY only in development."
        ),
    )
    AGENT_STREAM_JWT_ALGORITHM: str = Field(default="HS256")


settings = Settings()
