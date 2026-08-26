"""Platform API completion synchronization client (Domain D credential)."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import httpx
import jwt

from agent_service.config import settings
from agent_service.domain.run import AgentRun
from agent_service.presentation.schemas import CitationResponse

logger = logging.getLogger(__name__)


def mint_internal_service_jwt(
    secret_key: str,
    algorithm: str = "HS256",
    expires_in_seconds: int = 60,
) -> str:
    """Mint a Domain D short-lived JWT for Agent Service -> Platform API completion.

    Claims:
    - iss: "mwalimu-agent-service"
    - aud: "mwalimu-platform-internal"
    - sub: "agent-service"
    - exp: now + expires_in_seconds
    """
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": "mwalimu-agent-service",
        "aud": "mwalimu-platform-internal",
        "sub": "agent-service",
        "iat": now,
        "nbf": now,
        "exp": now + expires_in_seconds,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


class PlatformCompletionClient:
    """Dispatches terminal run completion callbacks to the Platform API."""

    def __init__(
        self,
        base_url: str | None = None,
        secret_key: str | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (base_url or settings.PLATFORM_COMPLETION_URL or "").rstrip(
            "/"
        )
        self._secret_key = secret_key or settings.INTERNAL_SERVICE_SECRET_KEY
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def is_configured(self) -> bool:
        """Return True if base URL and secret key are configured."""
        return bool(self._base_url and self._secret_key)

    async def send_completion(self, run: AgentRun) -> bool:
        """Send terminal run execution status to Platform API internal endpoint.

        Args:
            run: Terminal AgentRun instance.

        Returns:
            True if callback succeeded (200 OK), False otherwise.
        """
        if not self.is_configured:
            logger.debug(
                "Platform completion callback skipped: not configured for run %s",
                run.id,
            )
            return False

        if not run.is_terminal:
            logger.warning(
                "send_completion called on non-terminal run %s (status: %s)",
                run.id,
                run.status.value,
            )
            return False

        assert self._secret_key is not None
        url = f"{self._base_url}/api/v1/internal/runs/{run.id}/completion/"
        token = mint_internal_service_jwt(secret_key=self._secret_key)

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        citation_dicts: list[dict[str, Any]] = [
            CitationResponse.from_domain(c).model_dump(mode="json")
            for c in run.citations
        ]

        payload: dict[str, Any] = {
            "status": run.status.value,
            "answer": run.answer,
            "citations": citation_dicts,
            "error_code": run.error_code,
            "error_message": run.error_message,
            "step_count": run.step_count,
            "prompt_tokens": run.total_prompt_tokens,
            "completion_tokens": run.total_completion_tokens,
            "total_tokens": run.total_prompt_tokens + run.total_completion_tokens,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        }

        try:
            if self._client is not None:
                response = await self._client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                logger.info(
                    "Platform completion sync successful for run %s (status: %s)",
                    run.id,
                    run.status.value,
                )
                return True
            elif response.status_code == 409:
                logger.warning(
                    "Platform completion conflict for run %s: HTTP 409 (status: %s)",
                    run.id,
                    run.status.value,
                )
                return False
            else:
                logger.warning(
                    "Platform completion sync returned HTTP %d for run %s: %s",
                    response.status_code,
                    run.id,
                    response.text[:200],
                )
                return False

        except httpx.TimeoutException:
            logger.warning(
                "Platform completion callback timed out for run %s",
                run.id,
            )
            return False
        except httpx.RequestError as exc:
            logger.warning(
                "Platform completion callback connection error for run %s: %s",
                run.id,
                exc,
            )
            return False
        except Exception as exc:
            logger.error(
                "Unexpected error during platform completion sync for run %s: %s",
                run.id,
                exc,
                exc_info=True,
            )
            return False
