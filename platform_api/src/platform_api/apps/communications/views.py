"""Views for Notification Center API."""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):  # type: ignore[type-arg]
    """Notification Center API.

    Allows authenticated users to retrieve, inspect, and mark their in-platform
    notifications as read. Strictly tenant- and user-isolated: users only ever
    have visibility into notifications where they are the recipient.
    """

    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self) -> QuerySet[Notification]:
        """Return notifications for the authenticated user."""
        user = self.request.user
        if not user or not user.is_authenticated:
            return Notification.objects.none()

        qs = Notification.objects.filter(recipient=user).select_related(
            "actor", "actor__profile"
        ).order_by("-created_at")

        # Filter by read state
        is_read_param = self.request.query_params.get("is_read")
        unread_param = self.request.query_params.get("unread")
        if unread_param is not None and unread_param.lower() in ("true", "1"):
            qs = qs.filter(is_read=False)
        elif is_read_param is not None:
            if is_read_param.lower() in ("true", "1"):
                qs = qs.filter(is_read=True)
            elif is_read_param.lower() in ("false", "0"):
                qs = qs.filter(is_read=False)

        # Filter by notification type
        type_param = self.request.query_params.get("type")
        if type_param:
            qs = qs.filter(notification_type=type_param)

        return qs

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """List notifications with unread count metadata in response headers and envelope."""
        queryset = self.filter_queryset(self.get_queryset())
        unread_count = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data["unread_count"] = unread_count
            response["X-Unread-Count"] = str(unread_count)
            return response

        serializer = self.get_serializer(queryset, many=True)
        response = Response(
            {
                "results": serializer.data,
                "unread_count": unread_count,
            },
            status=status.HTTP_200_OK,
        )
        response["X-Unread-Count"] = str(unread_count)
        return response

    @action(detail=True, methods=["post"], url_path="read")
    def mark_as_read(self, request: Request, pk: str | None = None) -> Response:
        """Mark a single notification as read."""
        notification = self.get_object()
        notification.mark_as_read()
        unread_count = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count()
        return Response(
            {
                "status": "marked_as_read",
                "notification_id": str(notification.id),
                "is_read": True,
                "read_at": notification.read_at.isoformat() if notification.read_at else None,
                "unread_count": unread_count,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="read-all")
    def mark_all_as_read(self, request: Request) -> Response:
        """Mark all unread notifications for the authenticated user as read."""
        now = timezone.now()
        updated_count = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).update(is_read=True, read_at=now, updated_at=now)

        return Response(
            {
                "status": "all_marked_as_read",
                "updated_count": updated_count,
                "unread_count": 0,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request: Request) -> Response:
        """Return the unread notification count for the authenticated user."""
        count = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count()
        return Response({"unread_count": count}, status=status.HTTP_200_OK)
