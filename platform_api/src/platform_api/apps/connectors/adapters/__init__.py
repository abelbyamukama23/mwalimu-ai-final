"""Connector adapter registry and factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from platform_api.apps.connectors.models import ConnectorType

from .base import BaseConnectorAdapter, SyncResult
from .google_drive import GoogleDriveAdapter
from .notion import NotionAdapter
from .s3 import S3Adapter
from .web_crawler import WebCrawlerAdapter

if TYPE_CHECKING:
    from platform_api.apps.connectors.models import Connection


class UnsupportedConnectorError(ValueError):
    """Raised when an adapter is not available for a connector type."""


_ADAPTER_REGISTRY: dict[str, type[BaseConnectorAdapter]] = {
    ConnectorType.WEB_CRAWLER: WebCrawlerAdapter,
    ConnectorType.GOOGLE_DRIVE: GoogleDriveAdapter,
    ConnectorType.NOTION: NotionAdapter,
    ConnectorType.S3: S3Adapter,
}


def get_connector_adapter(connector_type: str) -> BaseConnectorAdapter:
    """Instantiate the adapter for the given connector type."""
    adapter_cls = _ADAPTER_REGISTRY.get(connector_type)
    if not adapter_cls:
        raise UnsupportedConnectorError(
            f"No adapter implementation registered for connector type: '{connector_type}'"
        )
    return adapter_cls()


__all__ = [
    "BaseConnectorAdapter",
    "GoogleDriveAdapter",
    "NotionAdapter",
    "S3Adapter",
    "SyncResult",
    "UnsupportedConnectorError",
    "WebCrawlerAdapter",
    "get_connector_adapter",
]

