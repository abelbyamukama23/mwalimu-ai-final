"""Remote file and resource browser endpoint for interactive connection pickers."""

from __future__ import annotations

import logging
import uuid

from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from platform_api.apps.connectors.adapters import get_connector_adapter
from platform_api.apps.connectors.models import Connection
from platform_api.apps.connectors.views import _get_managed_library
from platform_api.apps.libraries.models import Library
from platform_api.apps.users.models import User

logger = logging.getLogger(__name__)


class RemoteBrowserView(APIView):
    """Browse live remote files and folders from a connected external service."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Browse connected external service files",
        description="Query live folder contents and files from the remote service (e.g. Google Drive, Notion).",
        responses={200: dict},
    )
    def get(
        self, request: Request, library_id: uuid.UUID, connection_id: uuid.UUID
    ) -> Response:
        """Browse files in the connected service."""
        assert isinstance(request.user, User)
        library = _get_managed_library(request.user, library_id)


        try:
            connection = Connection.objects.select_related("connector").get(
                id=connection_id, library=library
            )
        except Connection.DoesNotExist as exc:
            raise PermissionDenied("Connection not found in this library.") from exc

        folder_id = request.query_params.get("folder_id", "root")
        query = request.query_params.get("query", "")

        try:
            adapter = get_connector_adapter(connection.connector.connector_type)
            result = adapter.browse(connection, folder_id=folder_id, query=query)
            return Response(result, status=status.HTTP_200_OK)
        except Exception as exc:
            logger.warning("Remote browse failed for connection %s: %s", connection_id, exc)
            return Response(
                {"detail": f"Failed to browse remote files: {exc}", "items": []},
                status=status.HTTP_400_BAD_REQUEST,
            )
