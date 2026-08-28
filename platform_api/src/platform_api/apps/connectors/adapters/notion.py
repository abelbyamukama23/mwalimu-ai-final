"""Notion connector adapter for workspace page and database ingestion."""

from __future__ import annotations

import hashlib
import io
import logging
from typing import TYPE_CHECKING, Any

import httpx

from platform_api.apps.processing.services import enqueue_processing
from platform_api.apps.resources.models import Resource, ResourceStatus, ResourceType
from platform_api.apps.resources.object_key import generate_resource_object_key
from platform_api.apps.resources.storage import get_object_storage

from .base import BaseConnectorAdapter, SyncResult

if TYPE_CHECKING:
    from platform_api.apps.connectors.models import Connection, ConnectionSyncJob

logger = logging.getLogger(__name__)

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_API_VERSION = "2022-06-28"


def _extract_rich_text(rich_text_list: list[dict[str, Any]]) -> str:
    """Extract plain text from Notion rich text block objects."""
    return "".join(item.get("plain_text", "") for item in rich_text_list)


def _render_blocks_to_markdown(blocks: list[dict[str, Any]]) -> str:
    """Render Notion block children into structured markdown."""
    lines: list[str] = []
    for block in blocks:
        btype = block.get("type", "")
        content = block.get(btype, {})
        text = _extract_rich_text(content.get("rich_text", []))

        if btype == "paragraph":
            lines.append(f"\n{text}\n")
        elif btype == "heading_1":
            lines.append(f"\n# {text}\n")
        elif btype == "heading_2":
            lines.append(f"\n## {text}\n")
        elif btype == "heading_3":
            lines.append(f"\n### {text}\n")
        elif btype == "bulleted_list_item":
            lines.append(f"* {text}")
        elif btype == "numbered_list_item":
            lines.append(f"1. {text}")
        elif btype == "to_do":
            checked = content.get("checked", False)
            mark = "x" if checked else " "
            lines.append(f"- [{mark}] {text}")
        elif btype == "code":
            lang = content.get("language", "")
            lines.append(f"\n```{lang}\n{text}\n```\n")
        elif btype == "quote":
            lines.append(f"> {text}")
        elif text:
            lines.append(text)

    return "\n".join(lines).strip()


class NotionAdapter(BaseConnectorAdapter):
    """Adapter to ingest pages and databases from Notion."""

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        """Initialize adapter with optional client injection for testing."""
        self._custom_client = http_client

    def _get_client(self, token: str) -> httpx.Client:
        """Return HTTP client with Notion API headers."""
        if self._custom_client is not None:
            return self._custom_client
        return httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": NOTION_API_VERSION,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Mwalimu-NotionAdapter/1.0",
            },
            timeout=30.0,
            follow_redirects=True,
        )

    def test_connection(self, connection: Connection) -> bool:
        """Validate Notion API token by fetching workspace users."""
        creds = connection.get_credentials()
        token = creds.get("api_key") or creds.get("oauth_token")
        if not token:
            return False

        try:
            with self._get_client(token) as client:
                resp = client.get(f"{NOTION_API_BASE}/users/me")
                return resp.status_code == 200
        except Exception as exc:
            logger.warning("Notion connection test failed: %s", exc)
            return False

    def sync(
        self,
        connection: Connection,
        sync_job: ConnectionSyncJob,
    ) -> SyncResult:
        """Synchronize Notion database pages or page blocks into library resources."""
        config = connection.configuration or {}
        database_id = config.get("database_id")
        page_id = config.get("page_id")
        creds = connection.get_credentials()
        token = creds.get("api_key") or creds.get("oauth_token")

        if not token:
            return SyncResult(
                error_code="MISSING_CREDENTIALS",
                error_message="Notion API Key or OAuth token is required.",
            )

        if not database_id and not page_id:
            return SyncResult(
                error_code="INVALID_CONFIG",
                error_message="Either 'database_id' or 'page_id' is required in configuration.",
            )

        storage = get_object_storage()
        library = connection.library
        creator = connection.created_by or library.institution.users.first()
        result = SyncResult()

        try:
            with self._get_client(token) as client:
                pages_to_sync: list[dict[str, Any]] = []

                if database_id:
                    # Query pages within database
                    clean_db_id = database_id.replace("-", "")
                    query_url = f"{NOTION_API_BASE}/databases/{clean_db_id}/query"
                    resp = client.post(query_url, json={"page_size": 100})
                    if resp.status_code != 200:
                        return SyncResult(
                            error_code="NOTION_API_ERROR",
                            error_message=(
                                f"Failed to query database '{database_id}': {resp.text}"
                            ),
                        )
                    pages_to_sync.extend(resp.json().get("results", []))
                elif page_id:
                    # Fetch single page metadata
                    clean_page_id = page_id.replace("-", "")
                    resp = client.get(f"{NOTION_API_BASE}/pages/{clean_page_id}")
                    if resp.status_code != 200:
                        return SyncResult(
                            error_code="NOTION_API_ERROR",
                            error_message=(
                                f"Failed to fetch page '{page_id}': {resp.text}"
                            ),
                        )
                    pages_to_sync.append(resp.json())

                for page in pages_to_sync:
                    p_id = page.get("id", "")
                    result.resources_discovered += 1

                    # Extract Page Title
                    title = "Notion Document"
                    props = page.get("properties", {})
                    for prop_val in props.values():
                        if prop_val.get("type") == "title":
                            title_texts = prop_val.get("title", [])
                            if title_texts:
                                title = _extract_rich_text(title_texts)
                            break

                    # Fetch Block Children (page body content)
                    clean_p_id = p_id.replace("-", "")
                    blocks_resp = client.get(
                        f"{NOTION_API_BASE}/blocks/{clean_p_id}/children?page_size=100"
                    )
                    body_markdown = ""
                    if blocks_resp.status_code == 200:
                        blocks = blocks_resp.json().get("results", [])
                        body_markdown = _render_blocks_to_markdown(blocks)

                    doc_content = (
                        f"# {title}\nNotion Page ID: {p_id}\n\n{body_markdown}"
                    )
                    data_bytes = doc_content.encode("utf-8")
                    checksum = hashlib.sha256(data_bytes).hexdigest()
                    safe_filename = f"notion_{clean_p_id}.txt"
                    display_name = f"[Notion] {title}"[:255]

                    # Check for existing resource
                    existing_resource = Resource.objects.filter(
                        library=library,
                        original_filename=safe_filename,
                    ).first()

                    if existing_resource:
                        if existing_resource.checksum == checksum:
                            continue  # Idempotent skip

                        existing_resource.name = display_name
                        existing_resource.size = len(data_bytes)
                        existing_resource.checksum = checksum
                        existing_resource.status = ResourceStatus.READY
                        existing_resource.save(
                            update_fields=[
                                "name",
                                "size",
                                "checksum",
                                "status",
                                "updated_at",
                            ]
                        )

                        storage.upload(
                            existing_resource.object_key,
                            io.BytesIO(data_bytes),
                            content_type="text/plain; charset=utf-8",
                            size=len(data_bytes),
                        )
                        enqueue_processing(existing_resource)
                        result.resources_updated += 1
                    else:
                        new_resource = Resource.objects.create(
                            library=library,
                            name=display_name,
                            resource_type=ResourceType.TXT,
                            original_filename=safe_filename,
                            content_type="text/plain; charset=utf-8",
                            size=len(data_bytes),
                            object_key="pending",
                            checksum=checksum,
                            status=ResourceStatus.READY,
                            created_by=creator,
                        )
                        new_resource.object_key = generate_resource_object_key(
                            library.id, new_resource.id
                        )
                        new_resource.save(update_fields=["object_key"])

                        storage.upload(
                            new_resource.object_key,
                            io.BytesIO(data_bytes),
                            content_type="text/plain; charset=utf-8",
                            size=len(data_bytes),
                        )
                        enqueue_processing(new_resource)
                        result.resources_created += 1

        except Exception as exc:
            logger.exception(
                "Notion sync failed for connection %s: %s", connection.id, exc
            )
            return SyncResult(
                resources_discovered=result.resources_discovered,
                resources_created=result.resources_created,
                resources_updated=result.resources_updated,
                resources_deleted=result.resources_deleted,
                error_code="SYNC_FAILED",
                error_message=str(exc),
            )

        return result
