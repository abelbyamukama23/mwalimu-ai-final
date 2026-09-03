"""Tests for Phase 4 Institutional Console backend capabilities."""

from datetime import timedelta
import uuid
import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from platform_api.apps.agents.models import (
    AgentRunRecord,
    AgentRunStatus,
    AgentSession,
    AgentSessionStatus,
)
from platform_api.apps.connectors.models import (
    Connection,
    ConnectionStatus,
    Connector,
    ConnectorAuthType,
    ConnectorType,
)
from platform_api.apps.institutions.models import (
    AuditAction,
    Institution,
    InstitutionalAuditEvent,
)
from platform_api.apps.libraries.models import (
    Library,
    LibraryScopeType,
    LibraryStatus,
    LibraryVisibility,
)
from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)
from platform_api.apps.processing.models import ProcessingRun, ProcessingStatus
from platform_api.apps.resources.models import Resource, ResourceStatus, ResourceType


# ==============================================================================
# AUDIT LEDGER TESTS
# ==============================================================================


@pytest.mark.django_db
def test_audit_event_immutability(institution_a, user_a) -> None:
    """Audit events are strictly append-only; updates and deletions are rejected."""
    event = InstitutionalAuditEvent.objects.create(
        institution=institution_a,
        actor=user_a,
        action=AuditAction.MEMBER_ROLE_CHANGED,
        target_type="membership",
        target_id=str(uuid.uuid4()),
        target_repr="user@example.com",
        metadata={"old_role": "student", "new_role": "teacher"},
    )
    assert event.pk is not None

    # Attempting to update existing record must raise ValidationError
    event.target_repr = "tampered@example.com"
    with pytest.raises(ValidationError, match="strictly immutable"):
        event.save()

    # Attempting to delete existing record must raise ValidationError
    with pytest.raises(ValidationError, match="cannot be deleted"):
        event.delete()


@pytest.mark.django_db
def test_audit_event_recorded_on_membership_mutation(
    admin_client_a, admin_membership_a, institution_a, user_b
) -> None:
    """Mutating a member role via API records an immutable audit event."""
    membership_b = Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )

    url = reverse("membership-detail", kwargs={"pk": membership_b.pk})
    resp = admin_client_a.patch(url, {"role": MembershipRole.TEACHER}, format="json")
    assert resp.status_code == status.HTTP_200_OK

    event = InstitutionalAuditEvent.objects.filter(
        institution=institution_a,
        action=AuditAction.MEMBER_ROLE_CHANGED,
    ).first()
    assert event is not None
    assert event.target_type == "membership"
    assert event.target_id == str(membership_b.id)
    assert event.metadata.get("old_role") == MembershipRole.STUDENT
    assert event.metadata.get("new_role") == MembershipRole.TEACHER


@pytest.mark.django_db
def test_audit_logs_endpoint_security_and_isolation(
    admin_client_a, client_b, admin_membership_a, institution_a, institution_b, user_a
) -> None:
    """Only admins of the target institution may view audit logs."""
    InstitutionalAuditEvent.objects.create(
        institution=institution_a,
        actor=user_a,
        action=AuditAction.LIBRARY_CREATED,
        target_type="library",
        target_repr="Curriculum Physics",
    )

    url_a = reverse("institution-audit-logs", kwargs={"pk": institution_a.pk})
    resp_a = admin_client_a.get(url_a)
    assert resp_a.status_code == status.HTTP_200_OK
    assert len(resp_a.data) >= 1

    # Cross-tenant: Admin A requesting Inst B audit logs -> 403 Forbidden
    url_b = reverse("institution-audit-logs", kwargs={"pk": institution_b.pk})
    resp_b = admin_client_a.get(url_b)
    assert resp_b.status_code == status.HTTP_403_FORBIDDEN

    # Non-admin user requesting Inst A audit logs -> 403 Forbidden
    resp_unauth = client_b.get(url_a)
    assert resp_unauth.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# OVERVIEW AGGREGATION TESTS
# ==============================================================================


@pytest.mark.django_db
def test_overview_endpoint_aggregation_and_tenant_isolation(
    admin_client_a, client_b, admin_membership_a, institution_a, institution_b, user_a, user_b
) -> None:
    """GET /institutions/{id}/overview/ returns consolidated intelligence."""
    # Add another active student to Inst A
    Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )

    # Add a library and resource
    lib = Library.objects.create(
        name="Chemistry Lab",
        slug="chem-lab",
        scope_type=LibraryScopeType.INSTITUTION,
        institution=institution_a,
        visibility=LibraryVisibility.RESTRICTED,
        status=LibraryStatus.ACTIVE,
    )
    Resource.objects.create(
        library=lib,
        name="Lab Guide",
        original_filename="lab_guide.pdf",
        resource_type=ResourceType.PDF,
        size=1024,
        checksum="a" * 64,
        object_key="chem/lab.pdf",
        status=ResourceStatus.READY,
        created_by=user_a,
    )

    url = reverse("institution-overview", kwargs={"pk": institution_a.pk})
    resp = admin_client_a.get(url)

    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["name"] == institution_a.name
    assert resp.data["members"]["total_active"] == 2
    assert resp.data["members"]["by_role"]["administrator"] == 1
    assert resp.data["members"]["by_role"]["student"] == 1
    assert resp.data["knowledge"]["total_libraries"] == 1
    assert resp.data["knowledge"]["restricted_libraries"] == 1
    assert resp.data["knowledge"]["total_resources"] == 1
    assert resp.data["knowledge"]["resources_by_status"]["ready"] == 1
    assert resp.data["health"]["status"] == "healthy"

    # Non-member cannot access Inst A overview
    resp_unauth = client_b.get(url)
    assert resp_unauth.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# AI USAGE AGGREGATION TESTS
# ==============================================================================


@pytest.mark.django_db
def test_ai_usage_endpoint_aggregation_and_filtering(
    admin_client_a, client_b, admin_membership_a, institution_a, institution_b, user_a
) -> None:
    """GET /institutions/{id}/usage/ aggregates prompt, completion, total tokens and runs."""
    session = AgentSession.objects.create(
        user=user_a,
        institution=institution_a,
        title="Physics Q&A",
        status=AgentSessionStatus.ACTIVE,
    )

    # Create run 1
    AgentRunRecord.objects.create(
        session=session,
        user=user_a,
        prompt="Explain Newton's Third Law",
        status=AgentRunStatus.COMPLETED,
        prompt_tokens=150,
        completion_tokens=250,
        total_tokens=400,
        step_count=2,
    )

    # Create run 2
    AgentRunRecord.objects.create(
        session=session,
        user=user_a,
        prompt="Explain Hooke's Law",
        status=AgentRunStatus.FAILED,
        prompt_tokens=100,
        completion_tokens=0,
        total_tokens=100,
        step_count=1,
    )

    url = reverse("institution-usage", kwargs={"pk": institution_a.pk})
    resp = admin_client_a.get(url)

    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["summary"]["total_tokens"] == 500
    assert resp.data["summary"]["prompt_tokens"] == 250
    assert resp.data["summary"]["completion_tokens"] == 250
    assert resp.data["summary"]["total_runs"] == 2
    assert resp.data["summary"]["completed_runs"] == 1
    assert resp.data["summary"]["failed_runs"] == 1
    assert resp.data["summary"]["active_users"] == 1
    assert len(resp.data["timeline"]) == 1
    assert resp.data["timeline"][0]["total_tokens"] == 500
    assert len(resp.data["top_users"]) == 1
    assert resp.data["top_users"][0]["total_tokens"] == 500

    # Cross-tenant access rejected
    url_b = reverse("institution-usage", kwargs={"pk": institution_b.pk})
    resp_b = admin_client_a.get(url_b)
    assert resp_b.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# CONNECTOR LISTING & CREDENTIAL MASKING TESTS
# ==============================================================================


@pytest.mark.django_db
def test_institution_connections_endpoint_and_credential_masking(
    admin_client_a, client_b, admin_membership_a, institution_a, institution_b, user_a
) -> None:
    """GET /institutions/{id}/connections/ lists connections with library name and masked credentials."""
    connector = Connector.objects.create(
        name="Google Drive",
        slug="google-drive",
        connector_type=ConnectorType.GOOGLE_DRIVE,
        auth_type=ConnectorAuthType.OAUTH2,
        is_active=True,
    )

    lib = Library.objects.create(
        name="Math Department",
        slug="math-dept",
        scope_type=LibraryScopeType.INSTITUTION,
        institution=institution_a,
        status=LibraryStatus.ACTIVE,
    )

    connection = Connection.objects.create(
        library=lib,
        connector=connector,
        name="Calculus Folder",
        status=ConnectionStatus.ACTIVE,
        created_by=user_a,
    )
    connection.set_credentials({"refresh_token": "secret_oauth_token_123"})
    connection.save()

    url = reverse("institution-connections", kwargs={"pk": institution_a.pk})
    resp = admin_client_a.get(url)

    assert resp.status_code == status.HTTP_200_OK
    assert len(resp.data) == 1
    conn_data = resp.data[0]
    assert conn_data["name"] == "Calculus Folder"
    assert str(conn_data["library_id"]) == str(lib.id)
    assert conn_data["library_name"] == "Math Department"
    assert conn_data["has_credentials"] is True
    # Zero secret leakage: raw credentials or encrypted keys must never be exposed
    assert "credentials" not in conn_data
    assert "encrypted_credentials" not in conn_data
    assert "secret_oauth_token_123" not in str(resp.content)

    # Cross-tenant access rejected
    url_b = reverse("institution-connections", kwargs={"pk": institution_b.pk})
    resp_b = admin_client_a.get(url_b)
    assert resp_b.status_code == status.HTTP_403_FORBIDDEN
