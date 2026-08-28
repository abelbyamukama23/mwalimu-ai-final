"""Tests for Notion connector adapter."""

from __future__ import annotations

import httpx
import pytest

from platform_api.apps.connectors.adapters.notion import NotionAdapter
from platform_api.apps.connectors.models import (
    Connection,
    ConnectionSyncJob,
    Connector,
    ConnectorAuthType,
    ConnectorType,
)
from platform_api.apps.institutions.models import Institution
from platform_api.apps.libraries.models import Library
from platform_api.apps.resources.models import Resource, ResourceType
from platform_api.apps.users.models import User


@pytest.fixture
def institution(db: None) -> Institution:
    return Institution.objects.create(name="Notion Uni", slug="notion-uni")


@pytest.fixture
def user(db: None, institution: Institution) -> User:
    return User.objects.create_user(email="teacher@notion.edu", password="ValidPass123!")


@pytest.fixture
def library(db: None, institution: Institution) -> Library:
    return Library.objects.create(institution=institution, name="Notion Lib", slug="notion-lib")


@pytest.fixture
def notion_connector(db: None) -> Connector:
    connector, _ = Connector.objects.update_or_create(
        slug="notion",
        defaults={
            "name": "Notion",
            "connector_type": ConnectorType.NOTION,
            "auth_type": ConnectorAuthType.API_KEY,
            "config_schema": {
                "type": "object",
                "properties": {"database_id": {"type": "string"}},
                "required": ["database_id"],
            },
            "auth_schema": {
                "type": "object",
                "properties": {"api_key": {"type": "string"}},
                "required": ["api_key"],
            },
            "is_active": True,
        },
    )
    return connector


@pytest.mark.django_db
def test_notion_sync_database_pages_and_blocks(
    library: Library,
    notion_connector: Connector,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Notion adapter queries database pages, fetches block markdown, and indexes resources."""
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "databases/db123/query" in url_str:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "page-abc-123",
                            "properties": {
                                "Name": {
                                    "type": "title",
                                    "title": [{"plain_text": "Lesson 1: Python Basics"}],
                                }
                            },
                        }
                    ]
                },
            )
        elif "blocks/pageabc123/children" in url_str:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "type": "heading_1",
                            "heading_1": {
                                "rich_text": [{"plain_text": "Introduction"}]
                            },
                        },
                        {
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {"plain_text": "Python is a dynamic language."}
                                ]
                            },
                        },
                    ]
                },
            )
        return httpx.Response(404)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = NotionAdapter(http_client=mock_client)

    enqueued: list[Resource] = []
    monkeypatch.setattr(
        "platform_api.apps.connectors.adapters.notion.enqueue_processing",
        lambda r: enqueued.append(r),
    )

    connection = Connection.objects.create(
        library=library,
        connector=notion_connector,
        name="Lesson Notes",
        configuration={"database_id": "db123"},
        created_by=user,
    )
    connection.set_credentials({"api_key": "secret_notion_key_xyz"})
    connection.save()

    sync_job = ConnectionSyncJob.objects.create(connection=connection)

    result = adapter.sync(connection, sync_job)

    assert result.is_success is True
    assert result.resources_discovered == 1
    assert result.resources_created == 1
    assert len(enqueued) == 1

    res = Resource.objects.get(library=library, original_filename="notion_pageabc123.txt")
    assert res.resource_type == ResourceType.TXT
    assert res.name == "[Notion] Lesson 1: Python Basics"
