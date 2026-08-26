"""Views for the Knowledge Retrieval Gateway."""

from __future__ import annotations

import logging
from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from platform_api.apps.processing.embedding import EmbeddingError
from platform_api.apps.users.models import User

from .authentication import DelegatedExecutionAuthentication
from .serializers import SearchRequestSerializer, SearchResponseSerializer
from .use_cases import SearchKnowledgeUseCase

logger = logging.getLogger(__name__)


class ServiceUnavailable(APIException):
    """Exception raised when an upstream service (embedding provider/database) fails."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Knowledge retrieval service is temporarily unavailable."
    default_code = "service_unavailable"


class KnowledgeSearchView(APIView):
    """Gateway endpoint for semantic search over authorized knowledge."""

    authentication_classes = [
        DelegatedExecutionAuthentication,
        *APIView.authentication_classes,
    ]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Search indexed knowledge",
        description=(
            "Execute scoped vector similarity search across authorized libraries with "
            "server-enforced access policies and complete citation provenance."
        ),
        request=SearchRequestSerializer,
        responses={200: SearchResponseSerializer},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Process knowledge search request."""
        serializer = SearchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        assert isinstance(user, User)

        request_dto = serializer.to_dto()
        use_case = SearchKnowledgeUseCase()

        # Read the authoritative knowledge scope carried by the delegated token
        # (server-side, cannot be broadened by the caller).
        scope_type: str | None = None
        auth_payload = getattr(request, "auth", None)
        if isinstance(auth_payload, dict):
            context = auth_payload.get("context") or {}
            raw_scope = context.get("knowledge_scope")
            if isinstance(raw_scope, str) and raw_scope.strip():
                scope_type = raw_scope.strip()

        try:
            response_dto = use_case.execute(
                user=user, request_dto=request_dto, scope_type=scope_type
            )
        except EmbeddingError as exc:
            logger.error("Embedding provider failure during search: %s", exc)
            raise ServiceUnavailable(
                detail="Embedding service unavailable.",
                code="EMBEDDING_UNAVAILABLE",
            ) from exc
        except Exception as exc:
            logger.error(
                "Unexpected error during knowledge search: %s", exc, exc_info=True
            )
            raise ServiceUnavailable(
                detail="Database retrieval service unavailable.",
                code="DATABASE_UNAVAILABLE",
            ) from exc

        response_serializer = SearchResponseSerializer(response_dto)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
