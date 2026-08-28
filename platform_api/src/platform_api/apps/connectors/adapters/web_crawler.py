"""Web Crawler connector adapter for website and documentation ingestion."""

from __future__ import annotations

import hashlib
import html
import io
import logging
import re
import urllib.parse
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


def _extract_title_and_text(raw_html: str, url: str) -> tuple[str, str]:
    """Extract page title and clean visible text from HTML.

    Performs lightweight, zero-external-dependency parsing of HTML structure.
    """
    # 1. Extract Title
    title_match = re.search(
        r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL
    )
    if title_match:
        title = html.unescape(title_match.group(1)).strip()
        # Clean title of multiple spaces
        title = re.sub(r"\s+", " ", title)
    else:
        # Fallback to URL path or domain
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.strip("/")
        title = path if path else parsed.netloc

    # 2. Strip scripts, styles, comments, and meta tags
    cleaned = re.sub(
        r"<(script|style|svg|noscript)[^>]*>.*?</\1>",
        "",
        raw_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)

    # 3. Replace block tags with newlines
    cleaned = re.sub(
        r"</?(div|p|h1|h2|h3|h4|h5|h6|li|tr|article|section|header|footer)[^>]*>",
        "\n",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)

    # 4. Remove all remaining tags
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)

    # 5. Unescape HTML entities and normalize whitespace
    cleaned = html.unescape(cleaned)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in cleaned.split("\n")]
    text = "\n".join(line for line in lines if line)

    header = f"# {title}\nSource: {url}\n\n"
    return title[:255] or "Web Page", header + text


def _extract_links(raw_html: str, current_url: str, allowed_domains: set[str]) -> list[str]:
    """Extract internal crawlable links from HTML."""
    links: list[str] = []
    parsed_current = urllib.parse.urlparse(current_url)

    # Match href attributes
    for match in re.finditer(r'href=[\'"]?([^\'" >]+)', raw_html, re.IGNORECASE):
        raw_href = match.group(1).split("#")[0].strip()  # Strip fragment
        if not raw_href or raw_href.startswith(
            ("javascript:", "mailto:", "tel:", "data:")
        ):
            continue

        # Resolve relative URLs
        absolute_url = urllib.parse.urljoin(current_url, raw_href)
        parsed_target = urllib.parse.urlparse(absolute_url)

        # Only HTTP / HTTPS
        if parsed_target.scheme not in ("http", "https"):
            continue

        # Check allowed domain
        if parsed_target.netloc.lower() in allowed_domains:
            links.append(absolute_url)

    return links


class WebCrawlerAdapter(BaseConnectorAdapter):
    """Crawler adapter that ingests web documentation pages into library resources."""

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        """Initialize adapter with optional HTTP client injection for testing."""
        self._custom_client = http_client

    def _get_client(self, credentials: dict[str, Any]) -> httpx.Client:
        """Construct HTTP client with appropriate authorization headers."""
        if self._custom_client is not None:
            return self._custom_client

        headers: dict[str, str] = {
            "User-Agent": "Mwalimu-WebCrawler/1.0 (+https://mwalimu.ai)",
            "Accept": "text/html,text/plain,application/xhtml+xml;q=0.9,*/*;q=0.8",
        }

        # Inject auth headers if provided
        if "api_key" in credentials:
            headers["Authorization"] = f"Bearer {credentials['api_key']}"
        elif "token" in credentials:
            headers["Authorization"] = f"Bearer {credentials['token']}"
        elif "basic_auth" in credentials:
            headers["Authorization"] = f"Basic {credentials['basic_auth']}"

        return httpx.Client(
            headers=headers,
            timeout=15.0,
            follow_redirects=True,
        )

    def test_connection(self, connection: Connection) -> bool:
        """Test reachability of the configured base URL."""
        config = connection.configuration or {}
        base_url = config.get("base_url")
        if not base_url:
            return False

        credentials = connection.get_credentials()
        try:
            with self._get_client(credentials) as client:
                resp = client.head(base_url)
                if resp.status_code >= 400:
                    resp = client.get(base_url)
                return resp.status_code < 400
        except Exception as exc:
            logger.warning("Connection test failed for %s: %s", base_url, exc)
            return False

    def sync(
        self,
        connection: Connection,
        sync_job: ConnectionSyncJob,
    ) -> SyncResult:
        """Crawl website pages, create library resources, and enqueue indexing."""
        config = connection.configuration or {}
        base_url = config.get("base_url")
        if not base_url:
            return SyncResult(
                error_code="INVALID_CONFIG",
                error_message="Missing required 'base_url' in connection configuration.",
            )

        max_pages = min(int(config.get("max_pages", 10)), 50)
        parsed_base = urllib.parse.urlparse(base_url)
        base_domain = parsed_base.netloc.lower()

        allowed_domains = {base_domain}
        custom_domains = config.get("allowed_domains", [])
        if isinstance(custom_domains, list):
            for d in custom_domains:
                if isinstance(d, str) and d.strip():
                    allowed_domains.add(d.strip().lower())

        credentials = connection.get_credentials()
        storage = get_object_storage()
        library = connection.library
        creator = connection.created_by or library.institution.users.first()

        queue: list[str] = [base_url]
        visited: set[str] = set()

        result = SyncResult()

        try:
            with self._get_client(credentials) as client:
                while queue and len(visited) < max_pages:
                    url = queue.pop(0)
                    normalized_url = url.rstrip("/")
                    if normalized_url in visited:
                        continue
                    visited.add(normalized_url)

                    try:
                        resp = client.get(url)
                        if resp.status_code >= 400:
                            logger.warning(
                                "Crawler received HTTP %s for URL: %s",
                                resp.status_code,
                                url,
                            )
                            continue

                        content_type = resp.headers.get("content-type", "").lower()
                        # Only process HTML and text
                        if not any(
                            ct in content_type
                            for ct in ("text/html", "text/plain", "application/xhtml")
                        ):
                            continue

                        raw_text = resp.text
                        if "text/html" in content_type or "application/xhtml" in content_type:
                            title, doc_text = _extract_title_and_text(raw_text, url)
                            # Discover links
                            links = _extract_links(raw_text, url, allowed_domains)
                            for link in links:
                                if link.rstrip("/") not in visited:
                                    queue.append(link)
                        else:
                            parsed_url = urllib.parse.urlparse(url)
                            title = parsed_url.path.strip("/") or "Text Document"
                            doc_text = f"# {title}\nSource: {url}\n\n{raw_text}"

                        data_bytes = doc_text.encode("utf-8")
                        checksum = hashlib.sha256(data_bytes).hexdigest()
                        result.resources_discovered += 1

                        # Deterministic filename based on URL hash
                        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
                        safe_filename = f"web_{url_hash}.txt"
                        resource_name = f"[Web] {title}"[:255]

                        # Check for existing resource with same URL filename in this library
                        existing_resource = Resource.objects.filter(
                            library=library,
                            original_filename=safe_filename,
                        ).first()

                        if existing_resource:
                            if existing_resource.checksum == checksum:
                                # Content unchanged, skip re-upload
                                logger.info(
                                    "Resource for URL %s is unchanged (checksum=%s).",
                                    url,
                                    checksum,
                                )
                                continue

                            # Update existing resource
                            existing_resource.name = resource_name
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

                            # Re-upload updated content to storage
                            storage.upload(
                                existing_resource.object_key,
                                io.BytesIO(data_bytes),
                                content_type="text/plain",
                                size=len(data_bytes),
                            )

                            # Trigger re-indexing
                            enqueue_processing(existing_resource)
                            result.resources_updated += 1
                        else:
                            # Create new Resource
                            new_resource = Resource.objects.create(
                                library=library,
                                name=resource_name,
                                resource_type=ResourceType.TXT,
                                original_filename=safe_filename,
                                content_type="text/plain; charset=utf-8",
                                size=len(data_bytes),
                                object_key="pending",
                                checksum=checksum,
                                status=ResourceStatus.READY,
                                created_by=creator,
                            )
                            # Set deterministic canonical object key
                            new_resource.object_key = generate_resource_object_key(
                                library.id, new_resource.id
                            )
                            new_resource.save(update_fields=["object_key"])

                            # Upload binary to object storage
                            storage.upload(
                                new_resource.object_key,
                                io.BytesIO(data_bytes),
                                content_type="text/plain; charset=utf-8",
                                size=len(data_bytes),
                            )

                            # Enqueue chunking and pgvector embedding
                            enqueue_processing(new_resource)
                            result.resources_created += 1

                    except httpx.RequestError as req_err:
                        logger.warning("Failed to fetch %s: %s", url, req_err)
                        continue

        except Exception as exc:
            logger.exception("Crawler execution error for connection %s: %s", connection.id, exc)
            return SyncResult(
                resources_discovered=result.resources_discovered,
                resources_created=result.resources_created,
                resources_updated=result.resources_updated,
                resources_deleted=result.resources_deleted,
                error_code="CRAWL_FAILED",
                error_message=str(exc),
            )

        return result
