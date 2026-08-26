"""Public and internal API views for agent sessions, runs, and completion."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from django.conf import settings
from django.db import models, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from platform_api.apps.users.models import User

from .authentication import mint_streaming_ticket
from .completion_auth import InternalServiceAuthentication
from .models import (
    AgentRunRecord,
    AgentRunStatus,
    AgentSession,
    AgentSessionMessage,
    AgentSessionStatus,
    MessageRole,
)
from .orchestration import AgentRunOrchestrationService
from .serializers import (
    CreateRunRequestSerializer,
    RunCompletionRequestSerializer,
    RunResponseSerializer,
    SessionCreateRequestSerializer,
    SessionDetailResponseSerializer,
    SessionResponseSerializer,
    SessionUpdateRequestSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public Session Views
# ---------------------------------------------------------------------------


class SessionListCreateView(generics.ListCreateAPIView):  # type: ignore[type-arg]
    """Public endpoint for listing and creating AgentSessions.

    GET /api/v1/sessions/
    - Returns paginated list of sessions for authenticated user.
    - Ordered by -updated_at.

    POST /api/v1/sessions/
    - Creates a new session bound to user's authorized institution and library.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SessionResponseSerializer

    def get_queryset(self) -> models.QuerySet[AgentSession]:
        """Return ACTIVE sessions owned by the authenticated user.

        Archived conversations are excluded from the default list (they are
        hidden rather than deleted). They remain retrievable by id via the
        detail endpoint.
        """
        user = self.request.user
        if not isinstance(user, User):
            return AgentSession.objects.none()
        return (
            AgentSession.objects.filter(user=user, status=AgentSessionStatus.ACTIVE)
            .select_related("institution", "primary_library")
            .order_by("-updated_at")
        )

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create a new AgentSession for the authenticated user."""
        user = request.user
        assert isinstance(user, User)

        serializer = SessionCreateRequestSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        institution = data["_resolved_institution"]
        primary_library = data.get("_resolved_primary_library")
        title = data.get("title", "").strip() or "New Session"
        metadata = data.get("metadata", {})

        session = AgentSession.objects.create(
            user=user,
            institution=institution,
            primary_library=primary_library,
            title=title,
            metadata=metadata,
        )

        logger.info(
            "Created AgentSession %s for user %s (institution=%s)",
            session.id,
            request.user.pk,
            institution.pk if institution is not None else None,
        )
        return Response(
            SessionResponseSerializer(session).data,
            status=status.HTTP_201_CREATED,
        )


class SessionDetailView(generics.RetrieveUpdateDestroyAPIView):  # type: ignore[type-arg]
    """Public endpoint for reading, updating, and deleting AgentSessions.

    GET /api/v1/sessions/{id}/
    - Returns session metadata and chronological transcript messages.
    - Returns 404 if session does not exist or caller is not owner.

    PATCH /api/v1/sessions/{id}/
    - Partial update: rename (title) and archive/unarchive (status).
    - Returns the updated session summary.

    DELETE /api/v1/sessions/{id}/
    - Permanently deletes the session (cascades runs and messages).
    - Returns 204.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SessionDetailResponseSerializer
    lookup_url_kwarg = "session_id"

    def get_queryset(self) -> models.QuerySet[AgentSession]:
        """Return user-scoped sessions with prefetched transcript messages."""
        user = self.request.user
        if not isinstance(user, User):
            return AgentSession.objects.none()
        return (
            AgentSession.objects.filter(user=user)
            .select_related("institution", "primary_library")
            .prefetch_related(
                models.Prefetch(
                    "messages",
                    queryset=AgentSessionMessage.objects.order_by("sequence"),
                )
            )
        )

    def get_serializer_class(self) -> type:
        """Use the write serializer for PATCH/PUT and the detail serializer for GET."""
        if self.request.method in ("PUT", "PATCH"):
            return SessionUpdateRequestSerializer
        return SessionDetailResponseSerializer

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Apply a partial session update and return the refreshed summary."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        write_serializer = SessionUpdateRequestSerializer(
            instance,
            data=request.data,
            partial=partial,
            context={"request": request},
        )
        write_serializer.is_valid(raise_exception=True)
        self.perform_update(write_serializer)
        instance.refresh_from_db()
        return Response(
            SessionResponseSerializer(instance).data,
            status=status.HTTP_200_OK,
        )


class SessionRunCreateView(APIView):
    """Public endpoint for submitting a prompt to an existing AgentSession.

    POST /api/v1/sessions/{id}/runs/
    - Validates caller session ownership.
    - Validates prompt and execution parameters.
    - Atomically creates AgentRunRecord and user prompt message.
    - Hydrates prior canonical conversation history.
    - Dispatches execution via AgentRunOrchestrationService.
    - Returns 202 Accepted with durable run representation.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, session_id: uuid.UUID) -> Response:
        """Submit a prompt and dispatch an agent run."""
        user = request.user
        assert isinstance(user, User)
        session = get_object_or_404(
            AgentSession,
            id=session_id,
            user=user,
        )

        serializer = CreateRunRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        orchestrator = AgentRunOrchestrationService()
        run_record = orchestrator.dispatch_session_run(
            session=session,
            user=user,
            prompt=data["prompt"],
            max_steps=data.get("max_steps", 10),
            timeout_seconds=data.get("timeout_seconds", 60.0),
            token_budget=data.get("token_budget", 4000),
            locale=data.get("locale", "en"),
            tool_allowlist=data.get("tool_allowlist"),
            knowledge_scope=data.get("knowledge_scope", "relevant"),
        )

        # Mint Domain S streaming capability token upon successful dispatch
        ticket = mint_streaming_ticket(
            user_id=user.pk,
            run_id=run_record.pk,
            session_id=session.pk,
        )
        base_url = str(
            getattr(settings, "AGENT_SERVICE_PUBLIC_BASE_URL", "http://localhost:8001")
        ).rstrip("/")
        expires_in = int(getattr(settings, "AGENT_STREAM_JWT_EXPIRATION_SECONDS", 300))
        run_record.streaming = {  # type: ignore[attr-defined]
            "sse_url": f"{base_url}/api/v1/runs/{run_record.pk}/events",
            "ticket": ticket,
            "expires_in": expires_in,
        }

        return Response(
            RunResponseSerializer(run_record).data,
            status=status.HTTP_202_ACCEPTED,
        )


# ---------------------------------------------------------------------------
# Public Run Views
# ---------------------------------------------------------------------------


class RunDetailView(APIView):
    """Public endpoint for reading durable AgentRunRecord status.

    GET /api/v1/runs/{id}/
    - Reads directly from PostgreSQL system of record.
    - Does not depend on Agent Service availability.
    - Returns 404 if run does not exist or caller is not owner.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, run_id: uuid.UUID) -> Response:
        """Return durable run state snapshot."""
        user = request.user
        assert isinstance(user, User)
        run_record = get_object_or_404(
            AgentRunRecord,
            id=run_id,
            user=user,
        )
        return Response(
            RunResponseSerializer(run_record).data,
            status=status.HTTP_200_OK,
        )


class RunCancelView(APIView):
    """Public endpoint for cancelling an in-flight AgentRun.

    POST /api/v1/runs/{id}/cancel/
    - Validates ownership.
    - Transitions durable run record to CANCELLED in PostgreSQL.
    - Sends best-effort cancellation signal to Agent Service.
    - Safe if run is already terminal or Agent Service is unavailable.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, run_id: uuid.UUID) -> Response:
        """Cancel the specified agent run."""
        user = request.user
        assert isinstance(user, User)
        run_record = get_object_or_404(
            AgentRunRecord,
            id=run_id,
            user=user,
        )
        orchestrator = AgentRunOrchestrationService()
        cancelled_run = orchestrator.cancel_run(
            run_record=run_record,
            user=user,
        )
        return Response(
            RunResponseSerializer(cancelled_run).data,
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Internal Views (Domain D)
# ---------------------------------------------------------------------------


def _normalize_citations(
    raw_citations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ensure all UUID objects in citations are converted to strings for JSONField."""
    normalized: list[dict[str, Any]] = []
    for c in raw_citations:
        item = dict(c)
        if "resource_id" in item and item["resource_id"] is not None:
            item["resource_id"] = str(item["resource_id"])
        if "library_id" in item and item["library_id"] is not None:
            item["library_id"] = str(item["library_id"])
        if "chunk_id" in item and item["chunk_id"] is not None:
            item["chunk_id"] = str(item["chunk_id"])
        normalized.append(item)
    return normalized


class RunCompletionInternalView(APIView):
    """Internal endpoint for receiving terminal run results from Agent Service.

    Guarantees:
    1. Authenticated via Domain D internal service JWT.
    2. Atomically updates AgentRunRecord with terminal state and metrics.
    3. Idempotent: Duplicate completion requests return 200 without mutation.
    4. Conflict-safe: Conflicting completions on terminal runs return 409.
    5. Concurrency-safe: Row lock on AgentSession serializes sequence allocation.
    6. Invariant B enforced: Creates at most one assistant message.
    """

    authentication_classes = [InternalServiceAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, run_id: uuid.UUID) -> Response:
        """Handle incoming run completion result."""
        serializer = RunCompletionRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        incoming_status = data["status"]
        normalized_citations = _normalize_citations(data.get("citations", []))

        with transaction.atomic():
            try:
                run_record = AgentRunRecord.objects.select_for_update().get(id=run_id)
            except AgentRunRecord.DoesNotExist:
                return Response(
                    {
                        "error_code": "RUN_NOT_FOUND",
                        "detail": f"Agent run record '{run_id}' not found.",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Idempotency & Conflict Check on already-terminal runs
            if run_record.is_terminal:
                if run_record.status == incoming_status:
                    logger.info(
                        "Idempotent completion for run %s (status=%s)",
                        run_id,
                        run_record.status,
                    )
                    return Response(
                        {
                            "run_id": str(run_record.id),
                            "status": run_record.status,
                            "idempotent": True,
                            "message": (
                                "Idempotent completion acknowledged. No state mutation."
                            ),
                        },
                        status=status.HTTP_200_OK,
                    )
                else:
                    logger.warning(
                        "Conflicting completion for run %s: "
                        "current '%s' vs incoming '%s'",
                        run_id,
                        run_record.status,
                        incoming_status,
                    )
                    return Response(
                        {
                            "run_id": str(run_record.id),
                            "status": run_record.status,
                            "error_code": "CONFLICTING_TERMINAL_STATE",
                            "detail": (
                                "Run is already terminal "
                                f"('{run_record.status}'). "
                                "Cannot transition to "
                                f"'{incoming_status}'."
                            ),
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

            # Active run -> lock session row to serialize sequence allocation
            session = AgentSession.objects.select_for_update().get(
                id=run_record.session_id
            )

            # Update durable run record fields
            run_record.status = incoming_status
            run_record.answer = data.get("answer")
            run_record.citations = normalized_citations
            run_record.error_code = data.get("error_code")
            run_record.error_message = data.get("error_message")
            run_record.step_count = data.get("step_count", 0)
            run_record.prompt_tokens = data.get("prompt_tokens", 0)
            run_record.completion_tokens = data.get("completion_tokens", 0)
            run_record.total_tokens = data.get("total_tokens", 0)

            if data.get("started_at"):
                run_record.started_at = data["started_at"]
            run_record.finished_at = data.get("finished_at") or timezone.now()
            run_record.save()

            # For COMPLETED status: Create exactly one canonical assistant message
            if incoming_status == AgentRunStatus.COMPLETED and run_record.answer:
                # Query next sequence safely under session lock
                max_seq = (
                    AgentSessionMessage.objects.filter(session=session)
                    .aggregate(models.Max("sequence"))
                    .get("sequence__max")
                )
                next_seq = 0 if max_seq is None else max_seq + 1

                AgentSessionMessage.objects.create(
                    session=session,
                    run=run_record,
                    role=MessageRole.ASSISTANT,
                    content=run_record.answer,
                    citations=run_record.citations,
                    sequence=next_seq,
                )
                logger.info(
                    "Created assistant message for run %s in session %s (seq=%d)",
                    run_record.id,
                    session.id,
                    next_seq,
                )

            logger.info(
                "Successfully synchronized terminal completion for run %s (status=%s)",
                run_record.id,
                run_record.status,
            )

            return Response(
                {
                    "run_id": str(run_record.id),
                    "status": run_record.status,
                    "idempotent": False,
                    "message": "Run completion successfully processed.",
                },
                status=status.HTTP_200_OK,
            )
