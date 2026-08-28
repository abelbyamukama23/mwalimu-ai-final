import pytest
from rest_framework.test import APIClient

from platform_api.apps.connectors.models import (
    Connection,
    ConnectionSyncJob,
    Connector,
    ConnectorAuthType,
    ConnectorType,
    SyncJobStatus,
)
from platform_api.apps.institutions.models import Institution
from platform_api.apps.libraries.models import (
    Library,
    LibraryAccessPolicy,
    LibraryAccessRole,
    LibraryVisibility,
)
from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)
from platform_api.apps.users.models import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def institution_a(db: None) -> Institution:
    """Return Institution A."""
    return Institution.objects.create(name="University A", slug="uni-a")


@pytest.fixture
def institution_b(db: None) -> Institution:
    """Return Institution B."""
    return Institution.objects.create(name="University B", slug="uni-b")


@pytest.fixture
def user_admin_a(db: None) -> User:
    """Return institution admin for Institution A."""
    return User.objects.create_user(
        email="admin_a@example.com",
        password="ValidPassword123!",
    )


@pytest.fixture
def user_student_a(db: None) -> User:
    """Return student user for Institution A."""
    return User.objects.create_user(
        email="student_a@example.com",
        password="ValidPassword123!",
    )


@pytest.fixture
def user_stranger(db: None) -> User:
    """Return unrelated user in Institution B."""
    return User.objects.create_user(
        email="stranger@example.com",
        password="ValidPassword123!",
    )


@pytest.fixture
def membership_admin_a(
    db: None, user_admin_a: User, institution_a: Institution
) -> Membership:
    """Assign active admin membership to user_admin_a."""
    return Membership.objects.create(
        user=user_admin_a,
        institution=institution_a,
        role=MembershipRole.ADMINISTRATOR,
        status=MembershipStatus.ACTIVE,
    )


@pytest.fixture
def membership_student_a(
    db: None, user_student_a: User, institution_a: Institution
) -> Membership:
    """Assign active student membership to user_student_a."""
    return Membership.objects.create(
        user=user_student_a,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )


@pytest.fixture
def membership_stranger_b(
    db: None, user_stranger: User, institution_b: Institution
) -> Membership:
    """Assign active membership to stranger in Institution B."""
    return Membership.objects.create(
        user=user_stranger,
        institution=institution_b,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )


@pytest.fixture
def library_a(db: None, institution_a: Institution) -> Library:
    """Return library in Institution A."""
    return Library.objects.create(
        institution=institution_a,
        name="Main Library",
        slug="main-library",
        visibility=LibraryVisibility.RESTRICTED,
    )


@pytest.fixture
def library_a_policy_student(
    db: None, library_a: Library, user_student_a: User
) -> LibraryAccessPolicy:
    """Grant student view policy to library A."""
    return LibraryAccessPolicy.objects.create(
        library=library_a,
        user=user_student_a,
        role=LibraryAccessRole.STUDENT,
    )


@pytest.fixture
def sample_connector(db: None) -> Connector:
    """Return sample active web crawler connector."""
    connector, _ = Connector.objects.update_or_create(
        slug="web-crawler",
        defaults={
            "name": "Web Documentation Crawler",
            "description": "Crawls documentation pages.",
            "connector_type": ConnectorType.WEB_CRAWLER,
            "auth_type": ConnectorAuthType.API_KEY,
            "config_schema": {
                "type": "object",
                "properties": {
                    "base_url": {"type": "string"},
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": 5},
                },
                "required": ["base_url"],
            },
            "auth_schema": {
                "type": "object",
                "properties": {
                    "api_key": {"type": "string", "minLength": 5},
                },
                "required": ["api_key"],
            },
            "is_active": True,
        },
    )
    return connector


# ---------------------------------------------------------------------------
# Connector Catalog API Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestConnectorCatalogAPI:
    """Verify GET /api/v1/connectors/ catalog endpoints."""

    def test_list_connectors_authenticated(
        self, user_student_a: User, sample_connector: Connector
    ) -> None:
        """Authenticated users can list active connectors."""
        client = APIClient()
        client.force_authenticate(user=user_student_a)

        response = client.get("/api/v1/connectors/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        slugs = [c["slug"] for c in data]
        assert "web-crawler" in slugs


    def test_list_connectors_unauthenticated(self) -> None:
        """Unauthenticated requests are rejected."""
        client = APIClient()
        response = client.get("/api/v1/connectors/")
        assert response.status_code == 401

    def test_retrieve_connector_detail(
        self, user_student_a: User, sample_connector: Connector
    ) -> None:
        """Retrieve single connector details."""
        client = APIClient()
        client.force_authenticate(user=user_student_a)

        response = client.get(f"/api/v1/connectors/{sample_connector.id}/")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_connector.id)
        assert data["name"] == "Web Documentation Crawler"


# ---------------------------------------------------------------------------
# Library Connection CRUD & Security Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLibraryConnectionAPI:
    """Verify library connection management and security boundaries."""

    def test_create_connection_success_by_admin(
        self,
        user_admin_a: User,
        membership_admin_a: Membership,
        library_a: Library,
        sample_connector: Connector,
    ) -> None:
        """Institution admin can create a connection with encrypted credentials."""
        client = APIClient()
        client.force_authenticate(user=user_admin_a)

        payload = {
            "name": "Django Docs Sync",
            "connector_id": str(sample_connector.id),
            "configuration": {
                "base_url": "https://docs.djangoproject.com",
                "max_depth": 2,
            },
            "credentials": {
                "api_key": "secret-token-12345",
            },
            "sync_frequency": "daily",
        }

        response = client.post(
            f"/api/v1/libraries/{library_a.id}/connections/",
            data=payload,
            format="json",
        )
        assert response.status_code == 201
        data = response.json()

        assert data["name"] == "Django Docs Sync"
        assert data["library_id"] == str(library_a.id)
        assert data["has_credentials"] is True
        assert data["sync_frequency"] == "daily"
        assert data["configuration"]["base_url"] == "https://docs.djangoproject.com"

        # STRICT INVARIANT: Credentials and encrypted_credentials
        # must NEVER appear in response payload
        assert "credentials" not in data
        assert "encrypted_credentials" not in data
        assert "secret-token-12345" not in str(data)

        # Verify in database that credentials are encrypted
        conn = Connection.objects.get(id=data["id"])
        assert conn.get_credentials() == {"api_key": "secret-token-12345"}
        assert "secret-token-12345" not in conn.encrypted_credentials

    def test_create_connection_rejected_for_non_manager(
        self,
        user_student_a: User,
        membership_student_a: Membership,
        library_a: Library,
        library_a_policy_student: LibraryAccessPolicy,
        sample_connector: Connector,
    ) -> None:
        """Student with read-only access cannot create connections."""
        client = APIClient()
        client.force_authenticate(user=user_student_a)

        payload = {
            "name": "Unauthorized Conn",
            "connector_id": str(sample_connector.id),
            "configuration": {"base_url": "https://example.com"},
        }

        response = client.post(
            f"/api/v1/libraries/{library_a.id}/connections/",
            data=payload,
            format="json",
        )
        assert response.status_code == 403

    def test_create_connection_invalid_schema_fails_400(
        self,
        user_admin_a: User,
        membership_admin_a: Membership,
        library_a: Library,
        sample_connector: Connector,
    ) -> None:
        """Configuration violating connector config_schema returns 400 Bad Request."""
        client = APIClient()
        client.force_authenticate(user=user_admin_a)

        # Missing required 'base_url'
        payload = {
            "name": "Invalid Conn",
            "connector_id": str(sample_connector.id),
            "configuration": {"max_depth": 2},
        }

        response = client.post(
            f"/api/v1/libraries/{library_a.id}/connections/",
            data=payload,
            format="json",
        )
        assert response.status_code == 400
        assert "configuration" in response.json()

    def test_create_connection_inactive_connector_fails_400(
        self,
        user_admin_a: User,
        membership_admin_a: Membership,
        library_a: Library,
        sample_connector: Connector,
    ) -> None:
        """Inactive connector cannot be used to create new connections."""
        sample_connector.is_active = False
        sample_connector.save()

        client = APIClient()
        client.force_authenticate(user=user_admin_a)

        payload = {
            "name": "Conn",
            "connector_id": str(sample_connector.id),
            "configuration": {"base_url": "https://example.com"},
        }

        response = client.post(
            f"/api/v1/libraries/{library_a.id}/connections/",
            data=payload,
            format="json",
        )
        assert response.status_code == 400
        assert "connector_id" in response.json()

    def test_list_and_retrieve_connections_tenant_isolated(
        self,
        user_admin_a: User,
        membership_admin_a: Membership,
        user_student_a: User,
        membership_student_a: Membership,
        library_a: Library,
        library_a_policy_student: LibraryAccessPolicy,
        user_stranger: User,
        membership_stranger_b: Membership,
        sample_connector: Connector,
    ) -> None:
        """Authorized library users can list connections; foreign users are rejected."""
        conn = Connection.objects.create(
            library=library_a,
            connector=sample_connector,
            name="Library A Connection",
            configuration={"base_url": "https://example.com"},
        )
        conn.set_credentials({"api_key": "top-secret"})
        conn.save()

        # Student with library access can list
        client = APIClient()
        client.force_authenticate(user=user_student_a)
        resp = client.get(f"/api/v1/libraries/{library_a.id}/connections/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Library A Connection"
        assert "credentials" not in data[0]
        assert "encrypted_credentials" not in data[0]

        # Student can retrieve detail
        detail_resp = client.get(
            f"/api/v1/libraries/{library_a.id}/connections/{conn.id}/"
        )
        assert detail_resp.status_code == 200
        detail_data = detail_resp.json()
        assert detail_data["name"] == "Library A Connection"
        assert "credentials" not in detail_data
        assert "encrypted_credentials" not in detail_data

        # Stranger from Institution B is rejected (403)
        client.force_authenticate(user=user_stranger)
        stranger_resp = client.get(f"/api/v1/libraries/{library_a.id}/connections/")
        assert stranger_resp.status_code == 403

        stranger_detail = client.get(
            f"/api/v1/libraries/{library_a.id}/connections/{conn.id}/"
        )
        assert stranger_detail.status_code == 403

    def test_update_connection_and_credentials_by_manager(
        self,
        user_admin_a: User,
        membership_admin_a: Membership,
        library_a: Library,
        sample_connector: Connector,
    ) -> None:
        """Manager can update connection settings and rotate credentials."""
        conn = Connection.objects.create(
            library=library_a,
            connector=sample_connector,
            name="Initial Conn",
            configuration={"base_url": "https://old.example.com"},
        )
        conn.set_credentials({"api_key": "old-secret"})
        conn.save()

        client = APIClient()
        client.force_authenticate(user=user_admin_a)

        patch_payload = {
            "name": "Updated Conn",
            "configuration": {"base_url": "https://new.example.com", "max_depth": 3},
            "credentials": {"api_key": "new-rotated-secret"},
        }

        resp = client.patch(
            f"/api/v1/libraries/{library_a.id}/connections/{conn.id}/",
            data=patch_payload,
            format="json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Conn"
        assert data["configuration"]["base_url"] == "https://new.example.com"
        assert "credentials" not in data
        assert "encrypted_credentials" not in data

        conn.refresh_from_db()
        assert conn.name == "Updated Conn"
        assert conn.get_credentials() == {"api_key": "new-rotated-secret"}

    def test_delete_connection_by_manager(
        self,
        user_admin_a: User,
        membership_admin_a: Membership,
        library_a: Library,
        sample_connector: Connector,
    ) -> None:
        """Manager can delete a connection."""
        conn = Connection.objects.create(
            library=library_a,
            connector=sample_connector,
            name="Conn to delete",
            configuration={"base_url": "https://example.com"},
        )
        conn_id = conn.id

        client = APIClient()
        client.force_authenticate(user=user_admin_a)

        resp = client.delete(f"/api/v1/libraries/{library_a.id}/connections/{conn_id}/")
        assert resp.status_code == 204
        assert not Connection.objects.filter(id=conn_id).exists()

    def test_sync_jobs_list_view(
        self,
        user_student_a: User,
        membership_student_a: Membership,
        library_a: Library,
        library_a_policy_student: LibraryAccessPolicy,
        sample_connector: Connector,
    ) -> None:
        """Authorized user can view historical sync jobs."""
        conn = Connection.objects.create(
            library=library_a,
            connector=sample_connector,
            name="Active Conn",
            configuration={"base_url": "https://example.com"},
        )
        job = ConnectionSyncJob.objects.create(
            connection=conn,
            status=SyncJobStatus.COMPLETED,
            resources_discovered=10,
            resources_created=8,
            resources_updated=2,
        )

        client = APIClient()
        client.force_authenticate(user=user_student_a)

        resp = client.get(
            f"/api/v1/libraries/{library_a.id}/connections/{conn.id}/sync-jobs/"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == str(job.id)
        assert data[0]["resources_created"] == 8
        assert data[0]["status"] == "completed"

    def test_trigger_sync_success_by_admin(
        self,
        user_admin_a: User,
        membership_admin_a: Membership,
        library_a: Library,
        sample_connector: Connector,
    ) -> None:
        """Library manager can trigger an on-demand sync job."""
        conn = Connection.objects.create(
            library=library_a,
            connector=sample_connector,
            name="Active Conn",
            configuration={"base_url": "https://example.com"},
        )

        client = APIClient()
        client.force_authenticate(user=user_admin_a)

        resp = client.post(
            f"/api/v1/libraries/{library_a.id}/connections/{conn.id}/sync/"
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["connection_id"] == str(conn.id)
        assert data["status"] == "queued"
        assert ConnectionSyncJob.objects.filter(connection=conn).count() == 1

    def test_trigger_sync_rejected_for_student(
        self,
        user_student_a: User,
        membership_student_a: Membership,
        library_a: Library,
        library_a_policy_student: LibraryAccessPolicy,
        sample_connector: Connector,
    ) -> None:
        """Student cannot trigger sync on a connection."""
        conn = Connection.objects.create(
            library=library_a,
            connector=sample_connector,
            name="Active Conn",
            configuration={"base_url": "https://example.com"},
        )

        client = APIClient()
        client.force_authenticate(user=user_student_a)

        resp = client.post(
            f"/api/v1/libraries/{library_a.id}/connections/{conn.id}/sync/"
        )
        assert resp.status_code == 403

    def test_trigger_sync_rejected_for_stranger(
        self,
        user_stranger: User,
        membership_stranger_b: Membership,
        library_a: Library,
        sample_connector: Connector,
    ) -> None:
        """User from another institution cannot trigger sync."""
        conn = Connection.objects.create(
            library=library_a,
            connector=sample_connector,
            name="Active Conn",
            configuration={"base_url": "https://example.com"},
        )

        client = APIClient()
        client.force_authenticate(user=user_stranger)

        resp = client.post(
            f"/api/v1/libraries/{library_a.id}/connections/{conn.id}/sync/"
        )
        assert resp.status_code == 403

