"""Orchestration service for managing AgentRun lifecycle and remote dispatch."""

from __future__ import annotations

import logging
from typing import Any

from django.db import models, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from platform_api.apps.context.resolution import ContextResolver
from platform_api.apps.knowledge.authentication import mint_delegated_token
from platform_api.apps.users.models import User

from .client import (
    AgentServiceClient,
    AgentServiceConnectionError,
    AgentServiceError,
    AgentServiceResponseError,
    AgentServiceTimeoutError,
)
from .hydration import hydrate_session_history
from .models import (
    AgentRunRecord,
    AgentRunStatus,
    AgentSession,
    AgentSessionMessage,
    MessageRole,
)

logger = logging.getLogger(__name__)


class OrchestrationError(Exception):
    """Base exception for run orchestration failures."""

    def __init__(self, message: str, run_record: AgentRunRecord | None = None) -> None:
        super().__init__(message)
        self.run_record = run_record


class AgentServiceUnavailableError(OrchestrationError):
    """Raised when the Agent Service cannot be reached."""


class AgentServiceDispatchFailedError(OrchestrationError):
    """Raised when the Agent Service rejects a dispatch request."""


class AgentRunOrchestrationService:
    """Orchestrates durable run creation, credential minting, and remote dispatch.

    Enforces the boundary:
    1. Platform API creates the durable AgentRunRecord in PostgreSQL.
    2. Platform API mints short-lived Platform Execution JWT for dispatch.
    3. Platform API mints DelegatedExecutionToken for Slice 5 Knowledge Gateway.
    4. Platform API resolves bounded pedagogical context via ContextResolver.
    5. Platform API dispatches execution to Agent Service via AgentServiceClient.
    6. Platform API updates the durable run status to QUEUED on success or
       FAILED on error.
    """

    def __init__(
        self,
        client: AgentServiceClient | None = None,
        context_resolver: ContextResolver | None = None,
    ) -> None:
        self.client = client or AgentServiceClient()
        self.context_resolver = context_resolver or ContextResolver()

    def dispatch_session_run(
        self,
        session: AgentSession,
        user: User,
        prompt: str,
        max_steps: int = 10,
        timeout_seconds: float = 60.0,
        token_budget: int = 4000,
        locale: str = "en",
        tool_allowlist: list[str] | None = None,
        extra_metadata: dict[str, Any] | None = None,
        knowledge_scope: str = "relevant",
    ) -> AgentRunRecord:
        """Create a durable run record and dispatch execution to Agent Service.

        Args:
            session: The persistent AgentSession.
            user: The authenticated owner/caller.
            prompt: The instruction prompt.
            max_steps: Maximum reasoning steps.
            timeout_seconds: Execution budget in seconds.
            token_budget: Context token budget.
            locale: Language/locale preference.
            tool_allowlist: Optional subset of capabilities allowed.
            extra_metadata: Optional additional metadata.

        Returns:
            The created and updated AgentRunRecord.

        Raises:
            AgentServiceUnavailableError: If Agent Service connection fails.
            AgentServiceDispatchFailedError: If Agent Service rejects the run.
        """
        # Step 1: Hydrate prior bounded canonical conversation history
        history = hydrate_session_history(session=session)

        # Step 2: Under session lock, create durable AgentRunRecord and user message
        with transaction.atomic():
            locked_session = AgentSession.objects.select_for_update().get(id=session.id)
            run_record = AgentRunRecord.objects.create(
                session=locked_session,
                user=user,
                prompt=prompt,
                status=AgentRunStatus.CREATED,
                timeout_seconds=timeout_seconds,
                max_steps=max_steps,
            )
            max_seq = (
                AgentSessionMessage.objects.filter(session=locked_session)
                .aggregate(models.Max("sequence"))
                .get("sequence__max")
            )
            next_seq = 0 if max_seq is None else max_seq + 1
            AgentSessionMessage.objects.create(
                session=locked_session,
                run=run_record,
                role=MessageRole.USER,
                content=prompt,
                sequence=next_seq,
            )

        # Step 3: Mint DelegatedExecutionToken for Knowledge Gateway (Domain C)
        delegated_token: str | None = None
        if session.primary_library_id is not None or (
            tool_allowlist is None or "knowledge_search" in tool_allowlist
        ):
            delegated_token = mint_delegated_token(
                user_id=user.pk,
                agent_run_id=run_record.pk,
                session_id=session.pk,
                expires_in_seconds=int(timeout_seconds + 300),
                knowledge_scope=knowledge_scope,
            )

        # Step 4: Resolve bounded pedagogical context
        subjects = extra_metadata.get("subjects") if extra_metadata else None
        topics = extra_metadata.get("topics") if extra_metadata else None
        purposes = extra_metadata.get("purposes") if extra_metadata else None
        context_budget = (
            extra_metadata.get("context_budget", 5) if extra_metadata else 5
        )

        resolved_context = self.context_resolver.resolve(
            user=user,
            prompt=prompt,
            institution=session.institution,
            subjects=subjects,
            topics=topics,
            purposes=purposes,
            budget_limit=context_budget,
        )

        # Read the user's persisted learner preferences (if any) so the Agent can
        # adapt its teaching behavior. Preferences never change authorization.
        preferences_payload: dict[str, Any] | None = None
        try:
            prefs = user.preferences
            preferences_payload = {
                "pedagogical_style": prefs.pedagogical_style,
                "explanation_depth": prefs.explanation_depth,
                "response_language": prefs.response_language,
            }
        except Exception:
            preferences_payload = None

        # Step 5: Dispatch to Agent Service via HTTP
        try:
            response = self.client.dispatch_run(
                user_id=user.pk,
                prompt=prompt,
                session_id=session.pk,
                run_id=run_record.pk,
                max_steps=max_steps,
                timeout_seconds=timeout_seconds,
                token_budget=token_budget,
                locale=locale,
                tool_allowlist=tool_allowlist,
                delegated_token=delegated_token,
                conversation_history=history if history else None,
                resolved_context=resolved_context,
                preferences=preferences_payload,
            )
            # Step 6: Update durable state to QUEUED on successful 202 Accepted
            with transaction.atomic():
                run_record.status = AgentRunStatus.QUEUED
                run_record.queued_at = timezone.now()
                run_record.save(update_fields=["status", "queued_at", "updated_at"])
            logger.info(
                "Successfully dispatched run %s for session %s (remote_id=%s)",
                run_record.pk,
                session.pk,
                response.id,
            )
            return run_record

        except (AgentServiceConnectionError, AgentServiceTimeoutError) as exc:
            logger.error(
                "Agent Service connection failure dispatching run %s: %s",
                run_record.pk,
                exc,
            )
            self._mark_run_failed(
                run_record=run_record,
                error_code="AGENT_SERVICE_UNAVAILABLE",
                error_message=(
                    "Could not connect to the Agent Service execution engine."
                ),
            )
            raise AgentServiceUnavailableError(
                "Agent Service is currently unavailable.",
                run_record=run_record,
            ) from exc

        except AgentServiceResponseError as exc:
            logger.error(
                "Agent Service rejected run %s with status %d: %s",
                run_record.pk,
                exc.status_code,
                exc.detail,
            )
            self._mark_run_failed(
                run_record=run_record,
                error_code=f"DISPATCH_REJECTED_{exc.status_code}",
                error_message=f"Agent Service rejected request: {exc.detail}",
            )
            raise AgentServiceDispatchFailedError(
                f"Agent Service dispatch rejected: {exc.detail}",
                run_record=run_record,
            ) from exc

        except AgentServiceError as exc:
            logger.error(
                "Agent Service error dispatching run %s: %s",
                run_record.pk,
                exc,
            )
            self._mark_run_failed(
                run_record=run_record,
                error_code="DISPATCH_ERROR",
                error_message=str(exc),
            )
            raise AgentServiceDispatchFailedError(
                f"Agent Service dispatch failed: {exc}",
                run_record=run_record,
            ) from exc

    def _mark_run_failed(
        self,
        run_record: AgentRunRecord,
        error_code: str,
        error_message: str,
    ) -> None:
        """Atomically transition run record to FAILED status."""
        try:
            with transaction.atomic():
                run_record.status = AgentRunStatus.FAILED
                run_record.error_code = error_code
                run_record.error_message = error_message
                run_record.finished_at = timezone.now()
                run_record.save(
                    update_fields=[
                        "status",
                        "error_code",
                        "error_message",
                        "finished_at",
                        "updated_at",
                    ]
                )
        except Exception as save_exc:
            logger.exception(
                "Failed to record failure state on AgentRunRecord %s: %s",
                run_record.pk,
                save_exc,
            )

    def cancel_run(
        self,
        run_record: AgentRunRecord,
        user: User,
    ) -> AgentRunRecord:
        """Cancel a durable run record and send cancellation signal to Agent Service.

        Guarantees:
        1. Verifies caller ownership.
        2. Idempotent: If run is already CANCELLED, returns immediately.
        3. Conflict-safe: If run is already terminal (COMPLETED, FAILED, TIMED_OUT),
           returns without mutating the terminal state.
        4. Transitions active run to CANCELLED under transaction.atomic() with row lock.
        5. Sends best-effort cancellation request to Agent Service.
        """
        if run_record.user_id != user.pk:
            raise PermissionDenied("You do not have permission to cancel this run.")

        with transaction.atomic():
            locked_run = AgentRunRecord.objects.select_for_update().get(
                id=run_record.id
            )
            if locked_run.is_terminal:
                logger.info(
                    "Run %s already terminal (status=%s); skipping cancel",
                    locked_run.id,
                    locked_run.status,
                )
                return locked_run

            locked_run.status = AgentRunStatus.CANCELLED
            locked_run.error_code = "CANCELLED"
            locked_run.error_message = "Execution cancelled by user."
            locked_run.finished_at = timezone.now()
            locked_run.save(
                update_fields=[
                    "status",
                    "error_code",
                    "error_message",
                    "finished_at",
                    "updated_at",
                ]
            )

        # Best-effort cooperative cancellation signal to Agent Service
        try:
            self.client.cancel_run(user_id=user.pk, run_id=run_record.pk)
        except Exception as exc:
            logger.warning(
                "Best-effort Agent Service cancellation for run %s failed: %s",
                run_record.pk,
                exc,
            )

        locked_run.refresh_from_db()
        return locked_run
