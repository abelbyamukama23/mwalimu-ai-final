"""Tests for the memberless chat boundary.

Proves that a Mwalimu user WITHOUT institution membership can create, list,
retrieve, and send messages in their own sessions (institution=None), while:
- institutional users keep the existing behavior,
- an arbitrary/unauthorized institution or library cannot be assigned,
- tenant isolation holds (no cross-user access).
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from platform_api.apps.agents.client import (
    AgentServiceClient,
    AgentServiceRunResponse,
)
from platform_api.apps.agents.models import (
    AgentSession,
    AgentSessionMessage,
    MessageRole,
)
from platform_api.apps.context.resolution import ContextResolver
from platform_api.apps.context.resolution.dto import ResolvedContext
from platform_api.apps.institutions.models import Institution
from platform_api.apps.libraries.models import (
    Library,
    LibraryAccessPolicy,
    LibraryAccessRole,
)
from platform_api.apps.memberships.models import Membership
from platform_api.apps.users.models import User


def _mock_dispatch_success(prompt: str = "Test") -> AgentServiceRunResponse:
    """Return a canned successful Agent Service dispatch response."""
    return AgentServiceRunResponse(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        status="queued",
        prompt=prompt,
        created_at="2026-08-23T15:00:00Z",
    )


@pytest.fixture
def memberless_user(db) -> User:
    """Return a user with NO institution membership."""
    return User.objects.create_user(
        email="memberless@example.com",
        password="password-123",
    )


@pytest.fixture
def memberless_client(memberless_user: User) -> APIClient:
    """Return an API client authenticated as a memberless user."""
    client = APIClient()
    client.force_authenticate(user=memberless_user)
    return client


def _create_memberless_session(client: APIClient) -> AgentSession:
    """Create a memberless session via the real API and return the model."""
    response = client.post(
        "/api/v1/sessions/", {"title": "Memberless Chat"}, format="json"
    )
    assert response.status_code == 201, response.content
    return AgentSession.objects.get(id=response.json()["id"])


# ---------------------------------------------------------------------------
# 1-4: memberless create / retrieve / list / run
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_memberless_can_create_session(memberless_client: APIClient) -> None:
    response = memberless_client.post(
        "/api/v1/sessions/", {"title": "My First Chat"}, format="json"
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "My First Chat"
    assert data["institution_id"] is None
    assert data["primary_library_id"] is None

    session = AgentSession.objects.get(id=data["id"])
    assert session.institution is None
    assert session.user.email == "memberless@example.com"


@pytest.mark.django_db
def test_memberless_can_retrieve_session(memberless_client: APIClient) -> None:
    session = _create_memberless_session(memberless_client)
    response = memberless_client.get(f"/api/v1/sessions/{session.id}/")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(session.id)
    assert data["institution_id"] is None
    assert data["messages"] == []


@pytest.mark.django_db
def test_memberless_can_list_session(memberless_client: APIClient) -> None:
    session = _create_memberless_session(memberless_client)
    response = memberless_client.get("/api/v1/sessions/")
    assert response.status_code == 200
    ids = [s["id"] for s in response.json().get("results", response.json())]
    assert str(session.id) in ids


@pytest.mark.django_db
def test_memberless_can_create_run(
    memberless_client: APIClient,
) -> None:
    """Memberless user creates a run; context resolution receives institution=None."""
    session = _create_memberless_session(memberless_client)
    captured: dict[str, object] = {}

    def fake_resolve(**kwargs: object) -> ResolvedContext:
        captured.update(kwargs)
        return ResolvedContext.empty(explanation="memberless", budget_limit=5)

    with patch.object(
        AgentServiceClient,
        "dispatch_run",
        return_value=_mock_dispatch_success("Explain photosynthesis"),
    ), patch.object(ContextResolver, "resolve", side_effect=fake_resolve):
        response = memberless_client.post(
            f"/api/v1/sessions/{session.id}/runs/",
            {"prompt": "Explain photosynthesis"},
            format="json",
        )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert captured["institution"] is None

    user_msg = AgentSessionMessage.objects.filter(
        session=session, role=MessageRole.USER
    ).first()
    assert user_msg is not None
    assert user_msg.content == "Explain photosynthesis"
    assert user_msg.sequence == 0


# ---------------------------------------------------------------------------
# 5: tenant isolation — memberless cannot access another user's session
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_memberless_cannot_access_other_user_session(
    memberless_client: APIClient,
    client_a: APIClient,
    user_a: User,
    institution_a: Institution,
    membership_a: Membership,
) -> None:
    # user_a with an institutional session
    res = client_a.post("/api/v1/sessions/", {"title": "User A Session"}, format="json")
    session_a_id = res.json()["id"]

    # memberless user B tries to read it
    resp = memberless_client.get(f"/api/v1/sessions/{session_a_id}/")
    assert resp.status_code == 404

    # memberless user B tries to post a run to it
    with patch.object(
        AgentServiceClient, "dispatch_run", return_value=_mock_dispatch_success()
    ):
        resp = memberless_client.post(
            f"/api/v1/sessions/{session_a_id}/runs/",
            {"prompt": "Hijack"},
            format="json",
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6: memberless cannot assign an arbitrary institution or library
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_memberless_cannot_specify_institution(
    memberless_client: APIClient,
    institution_a: Institution,
) -> None:
    response = memberless_client.post(
        "/api/v1/sessions/",
        {"title": "Spoof", "institution_id": str(institution_a.id)},
        format="json",
    )
    assert response.status_code == 400
    assert "institution_id" in response.json()


@pytest.mark.django_db
def test_memberless_cannot_specify_primary_library(
    memberless_client: APIClient,
    institution_a: Institution,
    library_a: Library,
    user_a: User,
    membership_a: Membership,
) -> None:
    # Give user_a (institutional) access to library_a for a valid library id.
    LibraryAccessPolicy.objects.create(
        user=user_a, library=library_a, role=LibraryAccessRole.STUDENT
    )
    response = memberless_client.post(
        "/api/v1/sessions/",
        {"title": "Spoof", "primary_library_id": str(library_a.id)},
        format="json",
    )
    assert response.status_code == 400
    assert "primary_library_id" in response.json()


# ---------------------------------------------------------------------------
# 7-9: institutional behavior preserved
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_institutional_user_default_assigns_institution(
    client_a: APIClient,
    user_a: User,
    institution_a: Institution,
    membership_a: Membership,
) -> None:
    response = client_a.post(
        "/api/v1/sessions/", {"title": "Institutional"}, format="json"
    )
    assert response.status_code == 201
    assert response.json()["institution_id"] == str(institution_a.id)


@pytest.mark.django_db
def test_institutional_user_explicit_institution(
    client_a: APIClient,
    institution_a: Institution,
    membership_a: Membership,
) -> None:
    response = client_a.post(
        "/api/v1/sessions/",
        {"title": "Explicit", "institution_id": str(institution_a.id)},
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["institution_id"] == str(institution_a.id)


@pytest.mark.django_db
def test_user_cannot_bind_to_unowned_institution(
    client_a: APIClient,
    institution_b: Institution,
    membership_a: Membership,
) -> None:
    response = client_a.post(
        "/api/v1/sessions/",
        {"title": "Bad", "institution_id": str(institution_b.id)},
        format="json",
    )
    assert response.status_code == 400
    assert "institution_id" in response.json()


@pytest.mark.django_db
def test_no_user_id_spoofing_memberless(
    memberless_client: APIClient,
    user_b: User,
) -> None:
    response = memberless_client.post(
        "/api/v1/sessions/",
        {"title": "Spoof", "user_id": str(user_b.id)},
        format="json",
    )
    assert response.status_code == 201
    session = AgentSession.objects.get(id=response.json()["id"])
    assert session.user.email == "memberless@example.com"


# ---------------------------------------------------------------------------
# Model allows null institution; existing institutional sessions remain valid
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_model_allows_null_institution(memberless_user: User) -> None:
    session = AgentSession.objects.create(
        user=memberless_user,
        institution=None,
        title="Direct memberless",
    )
    assert session.institution is None
    assert session.institution_id is None


@pytest.mark.django_db
def test_existing_institutional_session_remains_valid(
    user_a: User,
    institution_a: Institution,
    membership_a: Membership,
) -> None:
    session = AgentSession.objects.create(
        user=user_a,
        institution=institution_a,
        title="Existing institutional session",
    )
    session.refresh_from_db()
    assert session.institution == institution_a
