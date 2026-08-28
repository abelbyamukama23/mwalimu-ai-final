"""Tests for the Web Crawler connector adapter and sync execution."""

from __future__ import annotations

import httpx
import pytest

from platform_api.apps.connectors.adapters.web_crawler import (
    WebCrawlerAdapter,
    _extract_links,
    _extract_title_and_text,
)
from platform_api.apps.connectors.models import (
    Connection,
    ConnectionSyncJob,
    Connector,
    ConnectorAuthType,
    ConnectorType,
    SyncJobStatus,
)
from platform_api.apps.institutions.models import Institution
from platform_api.apps.libraries.models import Library
from platform_api.apps.resources.models import Resource
from platform_api.apps.resources.storage import get_object_storage
from platform_api.apps.users.models import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def institution(db: None) -> Institution:
    """Return test institution."""
    return Institution.objects.create(name="Tech Academy", slug="tech-academy")


@pytest.fixture
def user(db: None, institution: Institution) -> User:
    """Return test user."""
    return User.objects.create_user(
        email="dev@example.com",
        password="ValidPassword123!",
    )


@pytest.fixture
def library(db: None, institution: Institution) -> Library:
    """Return test library."""
    return Library.objects.create(
        institution=institution,
        name="Documentation Library",
        slug="docs-library",
    )


@pytest.fixture
def crawler_connector(db: None) -> Connector:
    """Return active Web Crawler connector catalog item."""
    connector, _ = Connector.objects.update_or_create(
        slug="web-crawler",
        defaults={
            "name": "Web Documentation Crawler",
            "connector_type": ConnectorType.WEB_CRAWLER,
            "auth_type": ConnectorAuthType.NONE,
            "config_schema": {
                "type": "object",
                "properties": {
                    "base_url": {"type": "string"},
                    "max_pages": {"type": "integer"},
                },
                "required": ["base_url"],
            },
            "is_active": True,
        },
    )
    return connector



# ---------------------------------------------------------------------------
# HTML Parsing Unit Tests
# ---------------------------------------------------------------------------


def test_extract_title_and_text() -> None:
    """Verify HTML cleanup, title extraction, and markdown structure."""
    raw_html = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>Quickstart Guide - Mwalimu</title>
        <script>console.log("ignore me");</script>
        <style>.hide { display: none; }</style>
      </head>
      <body>
        <header>Header Bar</header>
        <main>
          <h1>Getting Started</h1>
          <p>Welcome to <strong>Mwalimu</strong> documentation.</p>
          <ul>
            <li>Step 1: Setup</li>
            <li>Step 2: Connect</li>
          </ul>
        </main>
        <!-- Footer comment -->
      </body>
    </html>
    """
    title, text = _extract_title_and_text(raw_html, "https://docs.example.com/quickstart")
    assert title == "Quickstart Guide - Mwalimu"
    assert "Source: https://docs.example.com/quickstart" in text
    assert "Getting Started" in text
    assert "Welcome to Mwalimu documentation." in text
    assert "Step 1: Setup" in text
    assert "console.log" not in text
    assert "display: none" not in text


def test_extract_links() -> None:
    """Verify internal link extraction and filtering."""
    raw_html = """
    <html>
      <body>
        <a href="/api/overview">API Overview</a>
        <a href="https://docs.example.com/guides/setup">Setup Guide</a>
        <a href="https://external.com/page">External</a>
        <a href="mailto:support@example.com">Email</a>
        <a href="#section-anchor">Anchor</a>
      </body>
    </html>
    """
    allowed = {"docs.example.com"}
    links = _extract_links(raw_html, "https://docs.example.com/index", allowed)
    assert len(links) == 2
    assert "https://docs.example.com/api/overview" in links
    assert "https://docs.example.com/guides/setup" in links
    assert "https://external.com/page" not in links


# ---------------------------------------------------------------------------
# Adapter Sync & Storage Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_web_crawler_sync_end_to_end(
    library: Library,
    crawler_connector: Connector,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Crawler discovers pages, creates library Resources, and triggers processing."""
    # Mock HTTP Transport
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if url_str == "https://docs.example.com":
            content = """
            <html>
              <head><title>Home Page</title></head>
              <body>
                <h1>Home</h1>
                <p>Welcome to the main documentation.</p>
                <a href="/guide">Go to Guide</a>
              </body>
            </html>
            """
            return httpx.Response(200, text=content, headers={"content-type": "text/html"})
        elif url_str == "https://docs.example.com/guide":
            content = """
            <html>
              <head><title>Guide Page</title></head>
              <body>
                <h1>Guide</h1>
                <p>Detailed steps and instructions.</p>
              </body>
            </html>
            """
            return httpx.Response(200, text=content, headers={"content-type": "text/html"})
        return httpx.Response(404)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = WebCrawlerAdapter(http_client=mock_client)

    # Track enqueue_processing calls
    enqueued_resources: list[Resource] = []
    monkeypatch.setattr(
        "platform_api.apps.connectors.adapters.web_crawler.enqueue_processing",
        lambda r: enqueued_resources.append(r),
    )

    connection = Connection.objects.create(
        library=library,
        connector=crawler_connector,
        name="Docs Crawler Connection",
        configuration={"base_url": "https://docs.example.com", "max_pages": 5},
        created_by=user,
    )
    sync_job = ConnectionSyncJob.objects.create(
        connection=connection,
        status=SyncJobStatus.RUNNING,
    )

    result = adapter.sync(connection, sync_job)

    assert result.is_success is True
    assert result.resources_discovered == 2
    assert result.resources_created == 2
    assert result.resources_updated == 0

    # Verify Resources created in Library
    resources = Resource.objects.filter(library=library).order_by("name")
    assert resources.count() == 2
    assert len(enqueued_resources) == 2

    # Verify storage contents
    storage = get_object_storage()
    for res in resources:
        assert storage.exists(res.object_key)
        stream = storage.download(res.object_key)
        content_text = stream.read().decode("utf-8")
        assert "Source: https://docs.example.com" in content_text


@pytest.mark.django_db
def test_web_crawler_sync_idempotent(
    library: Library,
    crawler_connector: Connector,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-syncing unchanged pages does not duplicate or re-upload resources."""
    def handler(request: httpx.Request) -> httpx.Response:
        content = "<html><head><title>Static Page</title></head><body><p>Unchanged</p></body></html>"
        return httpx.Response(200, text=content, headers={"content-type": "text/html"})

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = WebCrawlerAdapter(http_client=mock_client)

    enqueued: list[Resource] = []
    monkeypatch.setattr(
        "platform_api.apps.connectors.adapters.web_crawler.enqueue_processing",
        lambda r: enqueued.append(r),
    )

    connection = Connection.objects.create(
        library=library,
        connector=crawler_connector,
        name="Static Sync",
        configuration={"base_url": "https://docs.example.com"},
        created_by=user,
    )
    job1 = ConnectionSyncJob.objects.create(connection=connection)

    # First Run
    res1 = adapter.sync(connection, job1)
    assert res1.resources_created == 1
    assert Resource.objects.filter(library=library).count() == 1

    # Second Run (identical content)
    job2 = ConnectionSyncJob.objects.create(connection=connection)
    res2 = adapter.sync(connection, job2)
    assert res2.resources_created == 0
    assert res2.resources_updated == 0
    assert Resource.objects.filter(library=library).count() == 1
