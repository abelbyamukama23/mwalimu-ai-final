"""Base interfaces for external knowledge connector adapters."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from platform_api.apps.connectors.models import Connection, ConnectionSyncJob


@dataclass
class SyncResult:
    """Result summary of a connector synchronization run."""

    resources_discovered: int = 0
    resources_created: int = 0
    resources_updated: int = 0
    resources_deleted: int = 0
    error_code: str | None = None
    error_message: str = ""

    @property
    def is_success(self) -> bool:
        """Return True if no fatal error occurred."""
        return self.error_code is None and not self.error_message


class BaseConnectorAdapter(abc.ABC):
    """Abstract contract for connector sync and authentication adapters."""

    @abc.abstractmethod
    def sync(
        self,
        connection: Connection,
        sync_job: ConnectionSyncJob,
    ) -> SyncResult:
        """Execute synchronization for a library connection.

        Discovers remote documents, uploads original binaries to object storage,
        creates or updates library Resource records, and dispatches them to
        the document processing pipeline.

        Args:
            connection: Instantiated library connection holding config and credentials.
            sync_job: Observability record tracking execution metrics and status.

        Returns:
            SyncResult summarizing discovered, created, updated, and deleted items.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def test_connection(self, connection: Connection) -> bool:
        """Validate connectivity and authentication with the external service.

        Args:
            connection: Instantiated library connection to test.

        Returns:
            True if connection and authentication succeed, False otherwise.
        """
        raise NotImplementedError

    def browse(
        self,
        connection: Connection,
        folder_id: str = "root",
        query: str = "",
    ) -> dict[str, Any]:
        """Browse remote resources/folders live for visual selection in the UI.

        Args:
            connection: Instantiated library connection holding credentials.
            folder_id: Remote parent folder/database identifier.
            query: Optional search keyword to filter items.

        Returns:
            Dict containing current folder info, breadcrumbs, and list of items.
        """
        return {"current_folder_id": folder_id, "breadcrumbs": [], "items": []}

