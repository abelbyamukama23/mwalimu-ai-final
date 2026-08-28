"""Google Drive connector adapter for library knowledge ingestion."""

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

GOOGLE_DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"


class GoogleDriveAdapter(BaseConnectorAdapter):
    """Adapter to ingest documents, PDFs, and exported Docs from Google Drive."""

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        """Initialize adapter with optional client injection for testing."""
        self._custom_client = http_client

    def _get_client(self, token: str) -> httpx.Client:
        """Return HTTP client with Bearer authorization."""
        if self._custom_client is not None:
            return self._custom_client
        return httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "Mwalimu-GoogleDriveAdapter/1.0",
            },
            timeout=30.0,
            follow_redirects=True,
        )

    def test_connection(self, connection: Connection) -> bool:
        """Validate access token against the Google Drive API."""
        creds = connection.get_credentials()
        token = creds.get("oauth_token") or creds.get("access_token")
        if not token:
            return False

        try:
            with self._get_client(token) as client:
                resp = client.get(f"{GOOGLE_DRIVE_API_BASE}/about?fields=user")
                return resp.status_code == 200
        except Exception as exc:
            logger.warning("Google Drive connection test failed: %s", exc)
            return False

    def browse(
        self,
        connection: Connection,
        folder_id: str = "root",
        query: str = "",
    ) -> dict[str, Any]:
        """Browse remote Google Drive folders and files live."""
        creds = connection.get_credentials()
        token = creds.get("oauth_token") or creds.get("access_token")
        if not token:
            return {"error": "Missing OAuth credentials", "items": []}

        # Seamless Sandbox Mode in Development
        if token.startswith("sandbox_") or creds.get("is_sandbox"):
            all_demo_items = [
                {
                    "id": "sandbox_folder_cs101",
                    "name": "Computer Science 101 Materials",
                    "type": "folder",
                    "mime_type": "application/vnd.google-apps.folder",
                    "size": 0,
                    "modified_at": "2026-08-20T10:00:00Z",
                },
                {
                    "id": "sandbox_folder_research",
                    "name": "Research & Department Archives",
                    "type": "folder",
                    "mime_type": "application/vnd.google-apps.folder",
                    "size": 0,
                    "modified_at": "2026-08-18T14:30:00Z",
                },
                {
                    "id": "sandbox_file_syllabus",
                    "name": "CS101_Course_Syllabus_2026.gdoc",
                    "type": "file",
                    "mime_type": "application/vnd.google-apps.document",
                    "size": 15420,
                    "modified_at": "2026-08-25T09:15:00Z",
                },
                {
                    "id": "sandbox_file_lecture1",
                    "name": "Lecture_1_Introduction_to_Computing.pdf",
                    "type": "file",
                    "mime_type": "application/pdf",
                    "size": 1048576,
                    "modified_at": "2026-08-26T11:00:00Z",
                },
                {
                    "id": "sandbox_file_ml_notes",
                    "name": "Machine_Learning_Foundations_Notes.docx",
                    "type": "file",
                    "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "size": 524288,
                    "modified_at": "2026-08-27T16:45:00Z",
                },
            ]

            if query:
                filtered = [
                    it for it in all_demo_items if query.lower() in it["name"].lower()
                ]
            elif folder_id == "sandbox_folder_cs101":
                filtered = [
                    all_demo_items[2],  # syllabus
                    all_demo_items[3],  # lecture1
                ]
            elif folder_id == "sandbox_folder_research":
                filtered = [
                    all_demo_items[4],  # ml notes
                ]
            else:
                filtered = all_demo_items

            return {
                "current_folder_id": folder_id,
                "breadcrumbs": [
                    {
                        "id": folder_id,
                        "name": "Folder" if folder_id != "root" else "My Drive",
                    }
                ],
                "items": filtered,
            }

        try:

            with self._get_client(token) as client:
                if query:
                    q = f"name contains '{query}' and trashed = false"
                else:
                    q = f"'{folder_id}' in parents and trashed = false"

                url = (
                    f"{GOOGLE_DRIVE_API_BASE}/files"
                    f"?q={q}&fields=files(id,name,mimeType,size,modifiedTime)&pageSize=100"
                )
                resp = client.get(url)
                if resp.status_code != 200:
                    return {"error": f"Drive API error: {resp.text}", "items": []}

                files = resp.json().get("files", [])
                items: list[dict[str, Any]] = []
                for f in files:
                    is_folder = (
                        f.get("mimeType") == "application/vnd.google-apps.folder"
                    )
                    items.append(
                        {
                            "id": f.get("id"),
                            "name": f.get("name"),
                            "type": "folder" if is_folder else "file",
                            "mime_type": f.get("mimeType"),
                            "size": int(f.get("size", 0)),
                            "modified_at": f.get("modifiedTime"),
                        }
                    )

                # Sort folders first, then files
                items.sort(key=lambda x: (x["type"] != "folder", x["name"].lower()))
                return {
                    "current_folder_id": folder_id,
                    "breadcrumbs": [{"id": folder_id, "name": "Folder" if folder_id != "root" else "My Drive"}],
                    "items": items,
                }
        except Exception as exc:
            logger.warning("Google Drive browse failed: %s", exc)
            return {"error": str(exc), "items": []}

    def sync(
        self,
        connection: Connection,
        sync_job: ConnectionSyncJob,
        selected_ids: list[str] | None = None,
    ) -> SyncResult:
        """Synchronize files from the specified Google Drive folder into the library."""
        config = connection.configuration or {}
        folder_id = config.get("folder_id", "root")
        creds = connection.get_credentials()
        token = creds.get("oauth_token") or creds.get("access_token")

        if not token:
            return SyncResult(
                error_code="MISSING_CREDENTIALS",
                error_message="Google Drive OAuth access token is required.",
            )

        storage = get_object_storage()
        library = connection.library
        creator = connection.created_by or library.institution.users.first()
        result = SyncResult()

        # Seamless Sandbox Mode Ingestion
        if token.startswith("sandbox_") or creds.get("is_sandbox"):
            sandbox_payloads = [
                (
                    "sandbox_syllabus_doc",
                    "[GDrive] CS101 Course Syllabus 2026",
                    ResourceType.TXT,
                    "text/plain; charset=utf-8",
                    b"Computer Science 101: Introduction to Algorithms & Systems\nSemester: Fall 2026\nInstructor: Prof. Ada Lovelace\n\nCourse Description:\nThis course provides an introduction to foundational algorithms, data structures, complexity analysis, and modern AI systems.\n\nGrading Policy:\n- Assignments: 40%\n- Midterm Exam: 25%\n- Final Project: 35%",
                ),
                (
                    "sandbox_lecture1_doc",
                    "[GDrive] Lecture 1: Computing Foundations & Architecture",
                    ResourceType.TXT,
                    "text/plain; charset=utf-8",
                    b"Lecture 1: Computing Foundations\n\n1. Von Neumann Architecture\nThe central processing unit (CPU) interacts with main memory and I/O devices via the system bus.\n\n2. Algorithmic Complexity\nBig-O notation describes the limiting behavior of a function when the argument tends towards a particular value or infinity.",
                ),
            ]

            for s_id, display_name, res_type, content_type, data_bytes in sandbox_payloads:
                if selected_ids and s_id not in selected_ids and "sandbox_file_syllabus" not in selected_ids:
                    continue

                result.resources_discovered += 1
                checksum = hashlib.sha256(data_bytes).hexdigest()
                safe_filename = f"gdrive_{s_id}.txt"

                existing = Resource.objects.filter(
                    library=library, original_filename=safe_filename
                ).first()

                if existing:
                    if existing.checksum == checksum:
                        continue
                    existing.name = display_name
                    existing.size = len(data_bytes)
                    existing.checksum = checksum
                    existing.status = ResourceStatus.READY
                    existing.save(update_fields=["name", "size", "checksum", "status", "updated_at"])
                    storage.upload(existing.object_key, io.BytesIO(data_bytes), content_type=content_type, size=len(data_bytes))
                    enqueue_processing(existing)
                    result.resources_updated += 1
                else:
                    new_res = Resource.objects.create(
                        library=library,
                        name=display_name,
                        resource_type=res_type,
                        original_filename=safe_filename,
                        content_type=content_type,
                        size=len(data_bytes),
                        object_key="pending",
                        checksum=checksum,
                        status=ResourceStatus.READY,
                        created_by=creator,
                    )
                    new_res.object_key = generate_resource_object_key(library.id, new_res.id)
                    new_res.save(update_fields=["object_key"])
                    storage.upload(new_res.object_key, io.BytesIO(data_bytes), content_type=content_type, size=len(data_bytes))
                    enqueue_processing(new_res)
                    result.resources_created += 1

            return result

        try:

            with self._get_client(token) as client:
                if selected_ids:
                    # Directly fetch selected file metadata
                    items = []
                    for s_id in selected_ids:
                        f_resp = client.get(
                            f"{GOOGLE_DRIVE_API_BASE}/files/{s_id}?fields=id,name,mimeType,size,md5Checksum"
                        )
                        if f_resp.status_code == 200:
                            items.append(f_resp.json())
                else:
                    # Query files located in the target folder
                    query = f"'{folder_id}' in parents and trashed = false"
                    url = (
                        f"{GOOGLE_DRIVE_API_BASE}/files"
                        f"?q={query}&fields=files(id,name,mimeType,size,md5Checksum)&pageSize=100"
                    )

                    resp = client.get(url)
                    if resp.status_code != 200:
                        return SyncResult(
                            error_code="API_ERROR",
                            error_message=(
                                f"Google Drive API returned HTTP {resp.status_code}: {resp.text}"
                            ),
                        )

                    items = resp.json().get("files", [])


                for item in items:
                    file_id = item.get("id")
                    file_name = item.get("name", f"gdrive_file_{file_id}")
                    mime_type = item.get("mimeType", "")

                    # Skip subfolders from direct download (future recursive support)
                    if mime_type == "application/vnd.google-apps.folder":
                        continue

                    result.resources_discovered += 1

                    # Handle native Google Docs/Sheets vs binary files
                    if mime_type == "application/vnd.google-apps.document":
                        # Export Google Doc as plain text
                        export_url = (
                            f"{GOOGLE_DRIVE_API_BASE}/files/{file_id}/export?mimeType=text/plain"
                        )
                        dl_resp = client.get(export_url)
                        res_type = ResourceType.TXT
                        ext = ".txt"
                        content_type = "text/plain; charset=utf-8"
                    elif mime_type == "application/pdf" or file_name.lower().endswith(".pdf"):
                        dl_url = f"{GOOGLE_DRIVE_API_BASE}/files/{file_id}?alt=media"
                        dl_resp = client.get(dl_url)
                        res_type = ResourceType.PDF
                        ext = ".pdf"
                        content_type = "application/pdf"
                    elif mime_type.startswith("text/") or file_name.lower().endswith(".txt"):
                        dl_url = f"{GOOGLE_DRIVE_API_BASE}/files/{file_id}?alt=media"
                        dl_resp = client.get(dl_url)
                        res_type = ResourceType.TXT
                        ext = ".txt"
                        content_type = "text/plain; charset=utf-8"
                    elif (
                        "wordprocessingml" in mime_type
                        or file_name.lower().endswith(".docx")
                    ):
                        dl_url = f"{GOOGLE_DRIVE_API_BASE}/files/{file_id}?alt=media"
                        dl_resp = client.get(dl_url)
                        res_type = ResourceType.DOCX
                        ext = ".docx"
                        content_type = (
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
                    else:
                        logger.info(
                            "Skipping unsupported Google Drive file type: %s (%s)",
                            file_name,
                            mime_type,
                        )
                        continue

                    if dl_resp.status_code != 200:
                        logger.warning(
                            "Failed to download Google Drive file %s: HTTP %s",
                            file_id,
                            dl_resp.status_code,
                        )
                        continue

                    file_bytes = dl_resp.content
                    checksum = hashlib.sha256(file_bytes).hexdigest()
                    safe_filename = f"gdrive_{file_id}{ext}"
                    display_name = f"[GDrive] {file_name}"[:255]

                    # Check for existing resource with same ID in this library
                    existing_resource = Resource.objects.filter(
                        library=library,
                        original_filename=safe_filename,
                    ).first()

                    if existing_resource:
                        if existing_resource.checksum == checksum:
                            continue  # Idempotent skip

                        existing_resource.name = display_name
                        existing_resource.size = len(file_bytes)
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
                            io.BytesIO(file_bytes),
                            content_type=content_type,
                            size=len(file_bytes),
                        )
                        enqueue_processing(existing_resource)
                        result.resources_updated += 1
                    else:
                        new_resource = Resource.objects.create(
                            library=library,
                            name=display_name,
                            resource_type=res_type,
                            original_filename=safe_filename,
                            content_type=content_type,
                            size=len(file_bytes),
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
                            io.BytesIO(file_bytes),
                            content_type=content_type,
                            size=len(file_bytes),
                        )
                        enqueue_processing(new_resource)
                        result.resources_created += 1

        except Exception as exc:
            logger.exception(
                "Google Drive sync failed for connection %s: %s", connection.id, exc
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
