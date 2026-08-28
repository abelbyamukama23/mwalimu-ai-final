import uuid

from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from platform_api.apps.libraries.authz import can_access_library, can_manage_library
from platform_api.apps.libraries.models import Library
from platform_api.apps.users.models import User

from .models import Connection, ConnectionSyncJob, Connector
from .serializers import (
    ConnectionCreateSerializer,
    ConnectionDetailSerializer,
    ConnectionListSerializer,
    ConnectionSyncJobSerializer,
    ConnectionUpdateSerializer,
    ConnectorSerializer,
)


def _get_accessible_library(user: User, library_id: uuid.UUID) -> Library:
    """Return the library if it exists and the user has view authorization."""
    try:
        library = Library.objects.get(pk=library_id)
    except Library.DoesNotExist as exc:
        raise PermissionDenied("Library not found.") from exc

    if not can_access_library(user, library):
        raise PermissionDenied("You do not have permission to access this library.")
    return library


def _get_managed_library(user: User, library_id: uuid.UUID) -> Library:
    """Return the library if the user has management authorization."""
    library = _get_accessible_library(user, library_id)
    if not can_manage_library(user, library):
        raise PermissionDenied(
            "You do not have permission to manage connections in this library."
        )
    return library


# ---------------------------------------------------------------------------
# Connector Catalog Views
# ---------------------------------------------------------------------------


class ConnectorListView(APIView):
    """List all available platform connectors."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="List connectors",
        description="Retrieve catalog of active connectors available on the platform.",
        responses={200: ConnectorSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        """Return all active connectors."""
        connectors = Connector.objects.filter(is_active=True).order_by("name")
        serializer = ConnectorSerializer(connectors, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ConnectorDetailView(APIView):
    """Retrieve details and schema for a specific connector."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Retrieve connector",
        description=(
            "Retrieve details, configuration schema, and auth schema for a connector."
        ),
        responses={200: ConnectorSerializer},
    )
    def get(self, request: Request, connector_id: uuid.UUID) -> Response:
        """Return connector details."""
        try:
            connector = Connector.objects.get(id=connector_id)
        except Connector.DoesNotExist:
            return Response(
                {"detail": "Connector not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = ConnectorSerializer(connector)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Library Connection Views
# ---------------------------------------------------------------------------


class LibraryConnectionListCreateView(APIView):
    """List or create external knowledge connections within a library."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="List library connections",
        description="List all connections configured within a library.",
        responses={200: ConnectionListSerializer(many=True)},
    )
    def get(self, request: Request, library_id: uuid.UUID) -> Response:
        """List connections for a library."""
        assert isinstance(request.user, User)
        library = _get_accessible_library(request.user, library_id)
        connections = Connection.objects.filter(library=library).select_related(
            "connector"
        )
        serializer = ConnectionListSerializer(connections, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Create library connection",
        description=(
            "Instantiate a new connection in a library with encrypted credentials."
        ),
        request=ConnectionCreateSerializer,
        responses={201: ConnectionDetailSerializer},
    )
    def post(self, request: Request, library_id: uuid.UUID) -> Response:
        """Create a new connection in the library."""
        assert isinstance(request.user, User)
        library = _get_managed_library(request.user, library_id)

        serializer = ConnectionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        connection = serializer.save(
            library=library,
            created_by=request.user,
        )

        response_serializer = ConnectionDetailSerializer(connection)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class LibraryConnectionDetailView(APIView):
    """Retrieve, update, or delete a library connection."""

    permission_classes = [permissions.IsAuthenticated]

    def _get_connection(
        self, user: User, library_id: uuid.UUID, connection_id: uuid.UUID
    ) -> tuple[Library, Connection]:
        """Fetch library and connection, verifying tenant boundary."""
        library = _get_accessible_library(user, library_id)
        try:
            connection = Connection.objects.select_related("connector").get(
                id=connection_id, library=library
            )
        except Connection.DoesNotExist as exc:
            raise PermissionDenied("Connection not found in this library.") from exc
        return library, connection

    @extend_schema(
        summary="Retrieve library connection",
        description=(
            "Retrieve details and configuration of a specific library connection."
        ),
        responses={200: ConnectionDetailSerializer},
    )
    def get(
        self, request: Request, library_id: uuid.UUID, connection_id: uuid.UUID
    ) -> Response:
        """Retrieve connection details."""
        assert isinstance(request.user, User)
        _, connection = self._get_connection(request.user, library_id, connection_id)
        serializer = ConnectionDetailSerializer(connection)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Update library connection",
        description="Update settings, schedule, or credentials of a connection.",
        request=ConnectionUpdateSerializer,
        responses={200: ConnectionDetailSerializer},
    )
    def put(
        self, request: Request, library_id: uuid.UUID, connection_id: uuid.UUID
    ) -> Response:
        """Update connection."""
        return self._handle_update(request, library_id, connection_id, partial=False)

    @extend_schema(
        summary="Partially update library connection",
        description=(
            "Partially update settings, schedule, or credentials of a connection."
        ),
        request=ConnectionUpdateSerializer,
        responses={200: ConnectionDetailSerializer},
    )
    def patch(
        self, request: Request, library_id: uuid.UUID, connection_id: uuid.UUID
    ) -> Response:
        """Partially update connection."""
        return self._handle_update(request, library_id, connection_id, partial=True)

    def _handle_update(
        self,
        request: Request,
        library_id: uuid.UUID,
        connection_id: uuid.UUID,
        partial: bool,
    ) -> Response:
        assert isinstance(request.user, User)
        library = _get_managed_library(request.user, library_id)
        try:
            connection = Connection.objects.select_related("connector").get(
                id=connection_id, library=library
            )
        except Connection.DoesNotExist as exc:
            raise PermissionDenied("Connection not found in this library.") from exc

        serializer = ConnectionUpdateSerializer(
            instance=connection,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        updated_connection = serializer.save()

        response_serializer = ConnectionDetailSerializer(updated_connection)
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Delete library connection",
        description="Delete a connection and its associated sync jobs.",
        responses={204: None},
    )
    def delete(
        self, request: Request, library_id: uuid.UUID, connection_id: uuid.UUID
    ) -> Response:
        """Delete connection."""
        assert isinstance(request.user, User)
        library = _get_managed_library(request.user, library_id)
        try:
            connection = Connection.objects.get(id=connection_id, library=library)
        except Connection.DoesNotExist as exc:
            raise PermissionDenied("Connection not found in this library.") from exc

        connection.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class LibraryConnectionSyncListView(APIView):
    """List historical sync jobs for a library connection."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="List connection sync jobs",
        description=(
            "Retrieve history of synchronization execution runs for a connection."
        ),
        responses={200: ConnectionSyncJobSerializer(many=True)},
    )
    def get(
        self, request: Request, library_id: uuid.UUID, connection_id: uuid.UUID
    ) -> Response:
        """List sync jobs."""
        assert isinstance(request.user, User)
        library = _get_accessible_library(request.user, library_id)
        try:
            connection = Connection.objects.get(id=connection_id, library=library)
        except Connection.DoesNotExist as exc:
            raise PermissionDenied("Connection not found in this library.") from exc

        sync_jobs = ConnectionSyncJob.objects.filter(connection=connection).order_by(
            "-created_at"
        )
        serializer = ConnectionSyncJobSerializer(sync_jobs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class LibraryConnectionSyncTriggerView(APIView):
    """Trigger an on-demand synchronization for a library connection."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Trigger connection sync",
        description=(
            "Trigger an asynchronous synchronization job to ingest updated resources."
        ),
        responses={202: ConnectionSyncJobSerializer},
    )
    def post(
        self, request: Request, library_id: uuid.UUID, connection_id: uuid.UUID
    ) -> Response:
        """Enqueue a synchronization task for the connection."""
        assert isinstance(request.user, User)
        library = _get_managed_library(request.user, library_id)
        try:
            connection = Connection.objects.select_related("connector").get(
                id=connection_id, library=library
            )
        except Connection.DoesNotExist as exc:
            raise PermissionDenied("Connection not found in this library.") from exc

        sync_job = ConnectionSyncJob.objects.create(
            connection=connection,
            status=ConnectionSyncJob._meta.get_field("status").default,  # QUEUED
        )

        try:
            from .tasks import sync_connection_task

            task_result = sync_connection_task.delay(
                str(connection.id), str(sync_job.id)
            )
            sync_job.celery_task_id = task_result.id
            sync_job.save(update_fields=["celery_task_id", "updated_at"])
        except Exception:
            # If celery is in eager mode or offline, we log and return the queued job
            pass

        serializer = ConnectionSyncJobSerializer(sync_job)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)


# ---------------------------------------------------------------------------
# OAuth 2.0 Views
# ---------------------------------------------------------------------------


class OAuthAuthorizeView(APIView):
    """Generate authorization consent URL for connecting third-party OAuth providers."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Generate OAuth consent URL",
        description="Generates signed OAuth 2.0 authorization URL for a library connection.",
        responses={200: dict},
    )
    def get(
        self, request: Request, library_id: uuid.UUID, provider: str
    ) -> Response:
        """Return OAuth authorization URL."""
        assert isinstance(request.user, User)
        library = _get_managed_library(request.user, library_id)

        from .oauth import OAuthError, get_oauth_authorization_url

        redirect_uri = request.build_absolute_uri(
            f"/api/v1/connectors/oauth/{provider}/callback/"
        )

        try:
            auth_url = get_oauth_authorization_url(
                provider=provider,
                library_id=library.id,
                user_id=request.user.id,
                redirect_uri=redirect_uri,
            )
            return Response(
                {"provider": provider, "authorization_url": auth_url},
                status=status.HTTP_200_OK,
            )
        except OAuthError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )


class OAuthCallbackView(APIView):
    """Receive authorization code, exchange tokens, and persist library connection."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="OAuth callback handler",
        description="Exchanges OAuth authorization code for tokens and saves encrypted credentials.",
        responses={200: ConnectionDetailSerializer},
    )
    def get(self, request: Request, provider: str) -> Response:
        """Handle OAuth callback."""
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        error = request.query_params.get("error")

        if error:
            return Response(
                {"detail": f"OAuth provider returned error: {error}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not code or not state:
            return Response(
                {"detail": "Missing 'code' or 'state' parameter in callback."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .models import ConnectorType
        from .oauth import OAuthError, decode_oauth_state, exchange_oauth_code

        try:
            state_data = decode_oauth_state(state)
        except OAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        library_id = uuid.UUID(state_data["library_id"])
        user_id = uuid.UUID(state_data["user_id"])

        try:
            library = Library.objects.get(id=library_id)
            user = User.objects.get(id=user_id)
        except (Library.DoesNotExist, User.DoesNotExist):
            return Response(
                {"detail": "Target library or user not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        redirect_uri = request.build_absolute_uri(
            f"/api/v1/connectors/oauth/{provider}/callback/"
        )

        try:
            credentials = exchange_oauth_code(
                provider=provider,
                code=code,
                redirect_uri=redirect_uri,
            )
        except OAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Match Connector
        connector_type = (
            ConnectorType.GOOGLE_DRIVE if provider == "google" else ConnectorType.NOTION
        )
        connector = Connector.objects.filter(
            connector_type=connector_type, is_active=True
        ).first()

        if not connector:
            return Response(
                {"detail": f"Connector for '{provider}' not found or inactive."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Create or update Connection
        conn_name = f"{provider.title()} Connection"
        connection, created = Connection.objects.get_or_create(
            library=library,
            name=conn_name,
            defaults={
                "connector": connector,
                "created_by": user,
                "status": Connection._meta.get_field("status").default,
            },
        )
        connection.connector = connector
        connection.set_credentials(credentials)
        connection.save()

        serializer = ConnectionDetailSerializer(connection)
        return Response(serializer.data, status=status.HTTP_200_OK)


