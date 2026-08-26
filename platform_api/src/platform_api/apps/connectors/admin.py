"""Django admin registration for connectors, connections, and sync jobs."""

from django.contrib import admin

from .models import Connection, ConnectionSyncJob, Connector


@admin.register(Connector)
class ConnectorAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin for Connector catalog."""

    list_display = [
        "name",
        "slug",
        "connector_type",
        "auth_type",
        "is_active",
        "created_at",
    ]
    list_filter = ["connector_type", "auth_type", "is_active"]
    search_fields = ["name", "slug", "description"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin for Library Connections."""

    list_display = [
        "name",
        "library",
        "connector",
        "status",
        "sync_frequency",
        "last_synced_at",
        "last_sync_status",
        "created_at",
    ]
    list_filter = ["status", "sync_frequency", "last_sync_status", "connector"]
    search_fields = ["name", "library__name", "connector__name"]
    readonly_fields = [
        "id",
        "encrypted_credentials",
        "last_synced_at",
        "last_sync_status",
        "last_sync_error",
        "created_at",
        "updated_at",
    ]


@admin.register(ConnectionSyncJob)
class ConnectionSyncJobAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin for Connection Sync Jobs."""

    list_display = [
        "id",
        "connection",
        "status",
        "resources_discovered",
        "resources_created",
        "resources_updated",
        "resources_deleted",
        "started_at",
        "finished_at",
        "created_at",
    ]
    list_filter = ["status"]
    search_fields = ["connection__name", "celery_task_id", "error_code"]
    readonly_fields = ["id", "created_at", "updated_at"]
