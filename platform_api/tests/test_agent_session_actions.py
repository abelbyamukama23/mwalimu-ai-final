"""Tests for conversation actions: rename, archive, and delete sessions."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from platform_api.apps.agents.models import AgentSession


def _create_session(client: APIClient, title: str = "My Chat") -> AgentSession:
    """Create a session for the authenticated client via the public endpoint."""
    response = client.post(
        reverse("agent-session-list-create"),
        {"title": title},
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    return AgentSession.objects.get(pk=response.data["id"])


@pytest.mark.django_db
def test_rename_session_updates_title(client_a: APIClient) -> None:
    """PATCH title renames the conversation."""
    session = _create_session(client_a, "Original")
    response = client_a.patch(
        reverse("agent-session-detail", kwargs={"session_id": session.id}),
        {"title": "Renamed"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["title"] == "Renamed"
    session.refresh_from_db()
    assert session.title == "Renamed"


@pytest.mark.django_db
def test_rename_rejects_blank_title(client_a: APIClient) -> None:
    """Empty and whitespace-only titles are rejected."""
    session = _create_session(client_a, "Original")
    for bad in ("", "   "):
        response = client_a.patch(
            reverse("agent-session-detail", kwargs={"session_id": session.id}),
            {"title": bad},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_archive_session_hides_it_from_list(client_a: APIClient) -> None:
    """Archived conversations are excluded from the default list but retrievable."""
    session = _create_session(client_a, "Archive me")
    response = client_a.patch(
        reverse("agent-session-detail", kwargs={"session_id": session.id}),
        {"status": "archived"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "archived"

    list_response = client_a.get(reverse("agent-session-list-create"))
    ids = [item["id"] for item in list_response.data["results"]]
    assert str(session.id) not in ids

    detail = client_a.get(
        reverse("agent-session-detail", kwargs={"session_id": session.id})
    )
    assert detail.status_code == status.HTTP_200_OK
    assert detail.data["status"] == "archived"


@pytest.mark.django_db
def test_unarchive_restores_session_to_list(client_a: APIClient) -> None:
    """Setting status back to active makes the conversation visible again."""
    session = _create_session(client_a, "Back")
    client_a.patch(
        reverse("agent-session-detail", kwargs={"session_id": session.id}),
        {"status": "archived"},
        format="json",
    )
    response = client_a.patch(
        reverse("agent-session-detail", kwargs={"session_id": session.id}),
        {"status": "active"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "active"

    list_response = client_a.get(reverse("agent-session-list-create"))
    ids = [item["id"] for item in list_response.data["results"]]
    assert str(session.id) in ids


@pytest.mark.django_db
def test_delete_session_permanently(client_a: APIClient) -> None:
    """DELETE removes the conversation and its transcript."""
    session = _create_session(client_a, "Delete me")
    response = client_a.delete(
        reverse("agent-session-detail", kwargs={"session_id": session.id})
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not AgentSession.objects.filter(pk=session.id).exists()

    list_response = client_a.get(reverse("agent-session-list-create"))
    ids = [item["id"] for item in list_response.data["results"]]
    assert str(session.id) not in ids

    detail = client_a.get(
        reverse("agent-session-detail", kwargs={"session_id": session.id})
    )
    assert detail.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_other_user_cannot_update_or_delete_session(
    client_a: APIClient,
    client_b: APIClient,
) -> None:
    """A non-owner cannot rename, archive, or delete another user's session."""
    session = _create_session(client_a, "Private")

    patch_response = client_b.patch(
        reverse("agent-session-detail", kwargs={"session_id": session.id}),
        {"title": "Hijacked"},
        format="json",
    )
    assert patch_response.status_code == status.HTTP_404_NOT_FOUND

    delete_response = client_b.delete(
        reverse("agent-session-detail", kwargs={"session_id": session.id})
    )
    assert delete_response.status_code == status.HTTP_404_NOT_FOUND
    assert AgentSession.objects.filter(pk=session.id).exists()


@pytest.mark.django_db
def test_update_rejects_invalid_status(client_a: APIClient) -> None:
    """An unsupported status value is rejected."""
    session = _create_session(client_a, "Status")
    response = client_a.patch(
        reverse("agent-session-detail", kwargs={"session_id": session.id}),
        {"status": "deleted"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
