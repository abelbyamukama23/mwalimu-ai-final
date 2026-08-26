"""Serializers for connectors, connections, and sync jobs."""

from __future__ import annotations

import uuid
from typing import Any

from rest_framework import serializers

from .models import (
    Connection,
    ConnectionStatus,
    ConnectionSyncJob,
    Connector,
    SyncFrequency,
)
from .validators import validate_data_against_schema

# ---------------------------------------------------------------------------
# Connector Serializers
# ---------------------------------------------------------------------------


class ConnectorSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for Connector catalog definitions."""

    class Meta:
        """Serializer metadata."""

        model = Connector
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "connector_type",
            "auth_type",
            "config_schema",
            "auth_schema",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ConnectorSummarySerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Compact summary of a connector specification."""

    class Meta:
        """Serializer metadata."""

        model = Connector
        fields = [
            "id",
            "name",
            "slug",
            "connector_type",
            "auth_type",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Connection Serializers
# ---------------------------------------------------------------------------


class ConnectionListSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """List serializer for library connections without sensitive credentials."""

    connector = ConnectorSummarySerializer(read_only=True)
    has_credentials = serializers.BooleanField(read_only=True)

    class Meta:
        """Serializer metadata."""

        model = Connection
        fields = [
            "id",
            "library_id",
            "connector",
            "name",
            "status",
            "sync_frequency",
            "last_synced_at",
            "last_sync_status",
            "last_sync_error",
            "has_credentials",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ConnectionDetailSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Detail serializer for a library connection."""

    connector = ConnectorSerializer(read_only=True)
    has_credentials = serializers.BooleanField(read_only=True)

    class Meta:
        """Serializer metadata."""

        model = Connection
        fields = [
            "id",
            "library_id",
            "connector",
            "name",
            "status",
            "configuration",
            "sync_frequency",
            "last_synced_at",
            "last_sync_status",
            "last_sync_error",
            "has_credentials",
            "created_by_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ConnectionCreateSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Payload validation for creating a new library connection."""

    connector_id = serializers.UUIDField(required=True)
    name = serializers.CharField(max_length=255, required=True)
    configuration = serializers.DictField(
        child=serializers.JSONField(),
        required=False,
        default=dict,
    )
    credentials = serializers.DictField(
        child=serializers.JSONField(),
        required=False,
        write_only=True,
        default=dict,
    )
    sync_frequency = serializers.ChoiceField(
        choices=SyncFrequency.choices,
        default=SyncFrequency.MANUAL,
    )
    status = serializers.ChoiceField(
        choices=ConnectionStatus.choices,
        default=ConnectionStatus.ACTIVE,
    )

    def validate_connector_id(self, value: uuid.UUID) -> Connector:
        """Verify that connector exists and is active."""
        try:
            connector = Connector.objects.get(id=value)
        except Connector.DoesNotExist as exc:
            raise serializers.ValidationError("Connector not found.") from exc

        if not connector.is_active:
            raise serializers.ValidationError(
                "This connector is currently inactive and cannot be used."
            )
        return connector

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Validate configuration and credentials against connector schemas."""
        connector: Connector = attrs["connector_id"]
        configuration = attrs.get("configuration", {})
        credentials = attrs.get("credentials", {})

        # Validate configuration schema
        if connector.config_schema:
            validate_data_against_schema(
                configuration,
                connector.config_schema,
                field_name="configuration",
            )

        # Validate auth credentials schema if provided and required
        if connector.auth_schema and credentials:
            validate_data_against_schema(
                credentials,
                connector.auth_schema,
                field_name="credentials",
            )

        return attrs

    def create(self, validated_data: dict[str, Any]) -> Connection:
        """Instantiate connection with encrypted credentials."""
        connector: Connector = validated_data.pop("connector_id")
        credentials = validated_data.pop("credentials", None)

        connection = Connection(
            connector=connector,
            **validated_data,
        )
        if credentials:
            connection.set_credentials(credentials)
        connection.save()
        return connection


class ConnectionUpdateSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Payload validation for updating an existing library connection."""

    name = serializers.CharField(max_length=255, required=False)
    configuration = serializers.DictField(
        child=serializers.JSONField(),
        required=False,
    )
    credentials = serializers.DictField(
        child=serializers.JSONField(),
        required=False,
        write_only=True,
    )
    sync_frequency = serializers.ChoiceField(
        choices=SyncFrequency.choices,
        required=False,
    )
    status = serializers.ChoiceField(
        choices=ConnectionStatus.choices,
        required=False,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Validate updated configuration and credentials."""
        assert isinstance(self.instance, Connection)
        instance = self.instance
        connector = instance.connector

        if "configuration" in attrs and connector.config_schema:
            validate_data_against_schema(
                attrs["configuration"],
                connector.config_schema,
                field_name="configuration",
            )

        if "credentials" in attrs and attrs["credentials"] and connector.auth_schema:
            validate_data_against_schema(
                attrs["credentials"],
                connector.auth_schema,
                field_name="credentials",
            )

        return attrs

    def update(
        self, instance: Connection, validated_data: dict[str, Any]
    ) -> Connection:
        """Update connection fields and re-encrypt credentials if changed."""
        if "name" in validated_data:
            instance.name = validated_data["name"]
        if "configuration" in validated_data:
            instance.configuration = validated_data["configuration"]
        if "sync_frequency" in validated_data:
            instance.sync_frequency = validated_data["sync_frequency"]
        if "status" in validated_data:
            instance.status = validated_data["status"]
        if "credentials" in validated_data:
            instance.set_credentials(validated_data["credentials"])

        instance.save()
        return instance


# ---------------------------------------------------------------------------
# Sync Job Serializers
# ---------------------------------------------------------------------------


class ConnectionSyncJobSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for connection sync job runs."""

    class Meta:
        """Serializer metadata."""

        model = ConnectionSyncJob
        fields = [
            "id",
            "connection_id",
            "status",
            "celery_task_id",
            "resources_discovered",
            "resources_created",
            "resources_updated",
            "resources_deleted",
            "error_code",
            "error_message",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
