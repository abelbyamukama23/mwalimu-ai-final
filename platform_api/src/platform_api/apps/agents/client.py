"""HTTP client for communicating with the independent Agent Service."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
from django.conf import settings

from .authentication import mint_platform_execution_jwt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions (Credentials & secrets are strictly NEVER included in messages)
# ---------------------------------------------------------------------------


class AgentServiceError(Exception):
    """Base exception for all Agent Service client operations."""


class AgentServiceConnectionError(AgentServiceError):
    """Raised when the Agent Service network connection fails or is refused."""


class AgentServiceTimeoutError(AgentServiceError):
    """Raised when a request to the Agent Service times out."""


class AgentServiceResponseError(AgentServiceError):
    """Raised when the Agent Service returns an HTTP error status (4xx/5xx)."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"Agent Service returned HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class AgentServiceValidationError(AgentServiceError):
    """Raised when the Agent Service returns an unexpected or malformed payload."""


# ---------------------------------------------------------------------------
# Response DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentServiceCitationResponse:
    """Citation evidence returned by the Agent Service."""

    chunk_id: uuid.UUID
    resource_id: uuid.UUID
    resource_name: str
    library_id: uuid.UUID
    library_name: str
    score: float
    text: str
    section: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    content_sha256: str = ""
    token_count: int = 0


@dataclass(frozen=True)
class AgentServiceRunResponse:
    """Parsed response from the Agent Service run endpoints."""

    id: uuid.UUID
    session_id: uuid.UUID
    status: str
    prompt: str
    created_at: str
    timeout_seconds: float = 60.0
    max_steps: int = 10
    answer: str | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    step_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    started_at: str | None = None
    finished_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentServiceRunResponse:
        """Parse raw response dict into structured response DTO."""
        try:
            raw_id = data.get("id") or data.get("run_id")
            if raw_id is None:
                raise KeyError("id or run_id")
            return cls(
                id=uuid.UUID(str(raw_id)),
                session_id=uuid.UUID(str(data["session_id"])),
                status=str(data["status"]),
                prompt=str(data.get("prompt", "")),
                created_at=str(data.get("created_at", "")),
                timeout_seconds=float(data.get("timeout_seconds", 60.0)),
                max_steps=int(data.get("max_steps", 10)),
                answer=data.get("answer"),
                citations=list(data.get("citations", [])),
                error_code=data.get("error_code"),
                error_message=data.get("error_message"),
                step_count=int(data.get("step_count", 0)),
                prompt_tokens=int(data.get("prompt_tokens", 0)),
                completion_tokens=int(data.get("completion_tokens", 0)),
                total_tokens=int(data.get("total_tokens", 0)),
                started_at=data.get("started_at"),
                finished_at=data.get("finished_at"),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise AgentServiceValidationError(
                f"Failed to parse Agent Service response payload: {exc}"
            ) from exc


@dataclass(frozen=True)
class AgentServiceCancelResponse:
    """Parsed response from the cancel run endpoint."""

    id: uuid.UUID
    status: str
    detail: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentServiceCancelResponse:
        """Parse raw response dict into cancel response DTO."""
        try:
            raw_id = data.get("id") or data.get("run_id")
            if raw_id is None:
                raise KeyError("id or run_id")
            return cls(
                id=uuid.UUID(str(raw_id)),
                status=str(data["status"]),
                detail=str(data.get("detail") or data.get("message", "")),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise AgentServiceValidationError(
                f"Failed to parse cancel response payload: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# HTTP Client
# ---------------------------------------------------------------------------


class AgentServiceClient:
    """Client for dispatching runs and managing execution in the Agent Service.

    Uses httpx for synchronous/asynchronous HTTP communication.
    Authenticates requests using short-lived Platform Execution JWTs.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (
            base_url
            if base_url is not None
            else getattr(settings, "AGENT_SERVICE_BASE_URL", "http://localhost:8001")
        ).rstrip("/")
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(getattr(settings, "AGENT_SERVICE_TIMEOUT_SECONDS", 30.0))
        )
        self._client = client

    def _get_headers(
        self,
        user_id: uuid.UUID | str,
        delegated_token: str | None = None,
    ) -> dict[str, str]:
        """Build authenticated headers for Platform -> Agent Service dispatch."""
        platform_jwt = mint_platform_execution_jwt(user_id=user_id)
        headers: dict[str, str] = {
            "Authorization": f"Bearer {platform_jwt}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if delegated_token:
            headers["X-Delegated-Token"] = delegated_token
        return headers

    def dispatch_run(
        self,
        user_id: uuid.UUID | str,
        prompt: str,
        session_id: uuid.UUID | str | None = None,
        run_id: uuid.UUID | str | None = None,
        max_steps: int = 10,
        timeout_seconds: float = 60.0,
        token_budget: int = 4000,
        locale: str = "en",
        tool_allowlist: list[str] | None = None,
        delegated_token: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        resolved_context: Any | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> AgentServiceRunResponse:
        """Dispatch a new agent execution run to the Agent Service.

        Args:
            user_id: Authenticated user UUID.
            prompt: Instruction prompt for the agent.
            session_id: Optional session identifier.
            run_id: Optional correlation run identifier.
            max_steps: Maximum reasoning steps.
            timeout_seconds: Execution timeout budget in seconds.
            token_budget: Context token budget.
            locale: User locale preference.
            tool_allowlist: Optional permitted tool names.
            delegated_token: Optional DelegatedExecutionToken for Knowledge Gateway.
            conversation_history: Optional bounded prior conversation messages.
            resolved_context: Optional bounded pedagogical ResolvedContext DTO or dict.

        Returns:
            AgentServiceRunResponse DTO.

        Raises:
            AgentServiceConnectionError: On network or connection failure.
            AgentServiceTimeoutError: On request timeout.
            AgentServiceResponseError: On non-2xx HTTP status.
            AgentServiceValidationError: On invalid or malformed response JSON.
        """
        payload: dict[str, Any] = {
            "prompt": prompt,
            "max_steps": max_steps,
            "timeout_seconds": timeout_seconds,
            "token_budget": token_budget,
            "locale": locale,
        }
        if session_id is not None:
            payload["session_id"] = str(session_id)
        if run_id is not None:
            payload["run_id"] = str(run_id)
        if tool_allowlist is not None:
            payload["tool_allowlist"] = list(tool_allowlist)
        if conversation_history is not None:
            payload["conversation_history"] = conversation_history
        if resolved_context is not None:
            if hasattr(resolved_context, "to_dict"):
                payload["context"] = resolved_context.to_dict()
            elif isinstance(resolved_context, dict):
                payload["context"] = resolved_context
        if preferences is not None:
            payload["preferences"] = preferences

        url = f"{self.base_url}/api/v1/runs"
        headers = self._get_headers(
            user_id=user_id,
            delegated_token=delegated_token,
        )

        try:
            if self._client is not None:
                response = self._client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            logger.error("Agent Service dispatch timed out: %s", url)
            raise AgentServiceTimeoutError("Agent Service request timed out.") from exc
        except httpx.RequestError as exc:
            logger.error("Agent Service connection error: %s", exc)
            raise AgentServiceConnectionError(
                "Failed to connect to Agent Service."
            ) from exc

        if response.status_code != 202:
            detail = self._extract_error_detail(response)
            logger.error(
                "Agent Service dispatch failed with status %d: %s",
                response.status_code,
                detail,
            )
            raise AgentServiceResponseError(
                status_code=response.status_code,
                detail=detail,
            )

        try:
            data = response.json()
        except Exception as exc:
            raise AgentServiceValidationError(
                "Agent Service response is not valid JSON."
            ) from exc

        return AgentServiceRunResponse.from_dict(data)

    def get_run_status(
        self,
        user_id: uuid.UUID | str,
        run_id: uuid.UUID | str,
    ) -> AgentServiceRunResponse:
        """Retrieve execution snapshot status of a run from Agent Service."""
        url = f"{self.base_url}/api/v1/runs/{run_id}"
        headers = self._get_headers(user_id=user_id)

        try:
            if self._client is not None:
                response = self._client.get(
                    url,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.get(url, headers=headers)
        except httpx.TimeoutException as exc:
            raise AgentServiceTimeoutError("Agent Service request timed out.") from exc
        except httpx.RequestError as exc:
            raise AgentServiceConnectionError(
                "Failed to connect to Agent Service."
            ) from exc

        if response.status_code != 200:
            detail = self._extract_error_detail(response)
            raise AgentServiceResponseError(
                status_code=response.status_code,
                detail=detail,
            )

        try:
            data = response.json()
        except Exception as exc:
            raise AgentServiceValidationError(
                "Agent Service response is not valid JSON."
            ) from exc

        return AgentServiceRunResponse.from_dict(data)

    def cancel_run(
        self,
        user_id: uuid.UUID | str,
        run_id: uuid.UUID | str,
    ) -> AgentServiceCancelResponse:
        """Send cooperative cancellation request to Agent Service."""
        url = f"{self.base_url}/api/v1/runs/{run_id}/cancel"
        headers = self._get_headers(user_id=user_id)

        try:
            if self._client is not None:
                response = self._client.post(
                    url,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, headers=headers)
        except httpx.TimeoutException as exc:
            raise AgentServiceTimeoutError("Agent Service request timed out.") from exc
        except httpx.RequestError as exc:
            raise AgentServiceConnectionError(
                "Failed to connect to Agent Service."
            ) from exc

        if response.status_code != 200:
            detail = self._extract_error_detail(response)
            raise AgentServiceResponseError(
                status_code=response.status_code,
                detail=detail,
            )

        try:
            data = response.json()
        except Exception as exc:
            raise AgentServiceValidationError(
                "Agent Service response is not valid JSON."
            ) from exc

        return AgentServiceCancelResponse.from_dict(data)

    def _extract_error_detail(self, response: httpx.Response) -> str:
        """Extract sanitized human-readable error detail from HTTP response."""
        try:
            data = response.json()
            if isinstance(data, dict):
                return str(data.get("detail", response.text[:200]))
        except Exception:
            pass
        return response.text[:200]
