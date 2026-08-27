"""Views for the resources app."""

import hashlib
import logging
import uuid
from typing import Any

from django.db.models import QuerySet
from django.http import FileResponse
from rest_framework import parsers, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from platform_api.apps.libraries.authz import can_access_library, can_manage_library
from platform_api.apps.libraries.models import Library
from platform_api.apps.users.models import User

from .models import Resource, ResourceStatus
from .object_key import generate_resource_object_key
from .serializers import ResourceSerializer
from .storage import get_object_storage
from .validators import ResourceValidationError, validate_resource_upload

logger = logging.getLogger(__name__)


def _get_library(user: User | Any, library_id: uuid.UUID) -> Library:
    """Return the library if it exists and the user can access it."""
    try:
        library = Library.objects.get(pk=library_id)
    except Library.DoesNotExist as exc:
        raise PermissionDenied("Library not found.") from exc

    if not can_access_library(user, library):
        raise PermissionDenied(
            "You do not have permission to access this library.",
        )
    return library


def _get_managed_library(user: User | Any, library_id: uuid.UUID) -> Library:
    """Return the library if the user may manage it."""
    library = _get_library(user, library_id)
    if not can_manage_library(user, library):
        raise PermissionDenied(
            "You do not have permission to manage resources in this library.",
        )
    return library


class ResourceViewSet(viewsets.ModelViewSet):  # type: ignore[type-arg]
    """View set for resource management within a library.

    Library administrators and institution administrators may create, update,
    and delete resources. Authorized library users may list and retrieve
    resources. The original binary is stored in S3-compatible object storage;
    only metadata is kept in PostgreSQL.
    """

    serializer_class = ResourceSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"
    parser_classes = [parsers.JSONParser, parsers.MultiPartParser]

    def _get_library_id(self) -> uuid.UUID:
        """Return the library UUID from the URL path parameter."""
        raw_library_id = self.kwargs.get("library_pk")
        return uuid.UUID(str(raw_library_id))

    def get_library(self, require_manage: bool = False) -> Library:
        """Return the library from the URL path parameter."""
        library_id = self._get_library_id()
        if require_manage:
            return _get_managed_library(self.request.user, library_id)
        return _get_library(self.request.user, library_id)

    def get_queryset(self) -> QuerySet[Resource]:
        """Return resources for libraries the user can access."""
        user = self.request.user
        if not isinstance(user, User):
            return Resource.objects.none()

        library_id = self._get_library_id()
        # Access check also validates that the library exists in the user's scope.
        self.get_library()

        active_statuses = (
            ResourceStatus.READY,
            ResourceStatus.PENDING,
            ResourceStatus.UPLOADING,
        )
        return Resource.objects.filter(
            library_id=library_id,
            status__in=active_statuses,
        ).order_by("-created_at")

    def get_object(self) -> Resource:
        """Return the resource scoped to the library in the URL."""
        resource = super().get_object()
        # Ensure the URL library_id matches the resource's library.
        if resource.library_id != self._get_library_id():
            raise PermissionDenied("Resource not found.")
        return resource  # type: ignore[no-any-return]

    def _storage(self) -> Any:
        """Return the configured object-storage backend."""
        return get_object_storage()

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Upload a resource into the library.

        Only library managers may upload resources.
        """
        library = self.get_library(require_manage=True)

        name = request.data.get("name") or request.POST.get("name")
        resource_type = request.data.get("resource_type") or request.POST.get(
            "resource_type"
        )
        uploaded_file = request.FILES.get("file")

        if not name:
            raise ValidationError({"name": "This field is required."})
        if not resource_type:
            raise ValidationError({"resource_type": "This field is required."})
        if not uploaded_file:
            raise ValidationError({"file": "No file was uploaded."})

        try:
            safe_filename, data = validate_resource_upload(
                resource_type=str(resource_type),
                filename=str(uploaded_file.name),
                content_type=str(uploaded_file.content_type),
                size=int(uploaded_file.size),
                content=uploaded_file,
            )
        except ResourceValidationError as exc:
            raise ValidationError(exc.message_dict) from exc

        checksum = hashlib.sha256(data).hexdigest()
        user = request.user
        assert isinstance(user, User)
        resource = Resource.objects.create(
            library=library,
            name=str(name),
            resource_type=str(resource_type),
            original_filename=safe_filename,
            content_type=str(uploaded_file.content_type),
            size=len(data),
            object_key=generate_resource_object_key(library.pk, uuid.uuid4()),
            checksum=checksum,
            status=ResourceStatus.UPLOADING,
            created_by=user,
        )

        # The key must include the actual resource id for deterministic storage.
        resource.object_key = generate_resource_object_key(library.pk, resource.pk)
        resource.save(update_fields=["object_key"])

        storage = self._storage()
        try:
            from io import BytesIO

            storage.upload(
                resource.object_key,
                BytesIO(data),
                content_type=resource.content_type,
                size=resource.size,
            )
        except Exception as exc:  # noqa: BLE001
            resource.status = ResourceStatus.FAILED
            resource.save(update_fields=["status"])
            raise ValidationError({"file": f"Storage upload failed: {exc}"}) from exc

        resource.status = ResourceStatus.READY
        resource.save(update_fields=["status"])

        # Automatically enqueue background processing, chunking & vector embedding
        try:
            from platform_api.apps.processing.services import enqueue_processing

            enqueue_processing(resource)
        except Exception as proc_exc:  # noqa: BLE001
            logger.warning(
                "Failed to enqueue processing for resource %s: %s",
                resource.id,
                proc_exc,
            )

        serializer = self.get_serializer(resource)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"], url_path="processing-status")
    def processing_status(
        self, request: Request, *args: object, **kwargs: object
    ) -> Response:
        """Return or trigger processing run status for the resource."""
        self.get_library()
        resource = self.get_object()

        from platform_api.apps.processing.models import ProcessingRun

        run: ProcessingRun | None
        if request.method == "POST":
            self.get_library(require_manage=True)
            from platform_api.apps.processing.services import enqueue_processing

            run = enqueue_processing(resource)
        else:
            run = (
                ProcessingRun.objects.filter(resource=resource)
                .order_by("-created_at")
                .first()
            )

        if not run:
            return Response(
                {
                    "status": "NOT_ENQUEUED",
                    "resource_id": str(resource.id),
                    "chunks_count": 0,
                }
            )

        from platform_api.apps.processing.models import DocumentChunk

        chunks_count = DocumentChunk.objects.filter(processing_run=run).count()

        return Response(
            {
                "run_id": str(run.id),
                "resource_id": str(resource.id),
                "status": run.status,
                "current_stage": run.current_stage,
                "is_active": run.is_active,
                "chunks_count": chunks_count,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "updated_at": run.updated_at.isoformat() if run.updated_at else None,
            }
        )

    def update(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Only library managers may update resource metadata."""
        self.get_library(require_manage=True)
        return super().update(request, *args, **kwargs)

    def partial_update(
        self, request: Request, *args: object, **kwargs: object
    ) -> Response:
        """Only library managers may partially update resource metadata."""
        self.get_library(require_manage=True)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Delete the resource and its stored object.

        Storage is deleted first so the system of record never points to a
        missing object. If storage deletion fails, the database record is kept.
        """
        self.get_library(require_manage=True)
        resource = self.get_object()
        storage = self._storage()

        try:
            storage.delete(resource.object_key)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError(
                {"detail": f"Failed to delete stored object: {exc}"}
            ) from exc

        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def download(
        self, request: Request, *args: object, **kwargs: object
    ) -> FileResponse:
        """Return the original binary for the resource."""
        self.get_library()
        resource = self.get_object()
        storage = self._storage()

        try:
            stream = storage.download(resource.object_key)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError(
                {"detail": f"Failed to retrieve stored object: {exc}"}
            ) from exc

        return FileResponse(
            stream,
            content_type=resource.content_type,
            filename=resource.original_filename,
            as_attachment=True,
        )
