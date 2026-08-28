import pytest
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.db.utils import IntegrityError

from platform_api.apps.connectors.crypto import (
    CredentialDecryptionError,
    decrypt_credentials,
    encrypt_credentials,
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
from platform_api.apps.users.models import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def institution(db: None) -> Institution:
    """Return test institution."""
    return Institution.objects.create(name="Test Institution", slug="test-institution")


@pytest.fixture
def library(db: None, institution: Institution) -> Library:
    """Return test library."""
    return Library.objects.create(
        institution=institution,
        name="Computer Science Library",
        slug="cs-library",
    )


@pytest.fixture
def user(db: None) -> User:
    """Return test user."""
    return User.objects.create_user(
        email="test.user@example.com",
        password="ValidPassword123!",
    )


@pytest.fixture
def sample_config_schema() -> dict[str, object]:
    """Return valid JSON Schema for connector configuration."""
    return {
        "type": "object",
        "properties": {
            "base_url": {"type": "string", "format": "uri"},
            "max_depth": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["base_url"],
    }


@pytest.fixture
def sample_auth_schema() -> dict[str, object]:
    """Return valid JSON Schema for connector authentication."""
    return {
        "type": "object",
        "properties": {
            "api_key": {"type": "string", "minLength": 8},
        },
        "required": ["api_key"],
    }


@pytest.fixture
def connector(
    db: None,
    sample_config_schema: dict[str, object],
    sample_auth_schema: dict[str, object],
) -> Connector:
    """Return sample active Connector."""
    connector, _ = Connector.objects.update_or_create(
        slug="web-crawler",
        defaults={
            "name": "Web Crawler",
            "description": "Crawls documentation websites.",
            "connector_type": ConnectorType.WEB_CRAWLER,
            "auth_type": ConnectorAuthType.API_KEY,
            "config_schema": sample_config_schema,
            "auth_schema": sample_auth_schema,
            "is_active": True,
        },
    )
    return connector



# ---------------------------------------------------------------------------
# Cryptography Tests
# ---------------------------------------------------------------------------


class TestCredentialCryptography:
    """Verify encryption and decryption of credentials."""

    def test_encrypt_and_decrypt_credentials_success(self) -> None:
        """Credentials dictionary encrypts and decrypts losslessly."""
        secret_payload = {"api_key": "sk-test-secret-12345", "token": "abc"}
        ciphertext = encrypt_credentials(secret_payload)

        assert isinstance(ciphertext, str)
        assert len(ciphertext) > 0
        assert (
            "sk-test-secret-12345" not in ciphertext
        )  # Ciphertext must not contain plaintext

        decrypted = decrypt_credentials(ciphertext)
        assert decrypted == secret_payload

    def test_encrypt_empty_payload_returns_empty_string(self) -> None:
        """Empty dictionary or None returns empty string."""
        assert encrypt_credentials({}) == ""
        assert encrypt_credentials(None) == ""
        assert decrypt_credentials("") == {}
        assert decrypt_credentials(None) == {}

    def test_decrypt_tampered_payload_raises_error(self) -> None:
        """Tampered ciphertext fails HMAC integrity verification."""
        ciphertext = encrypt_credentials({"secret": "value"})
        tampered = ciphertext[:-4] + "AAAA"

        with pytest.raises(CredentialDecryptionError, match="Tampered or invalid"):
            decrypt_credentials(tampered)

    def test_decrypt_invalid_string_raises_error(self) -> None:
        """Arbitrary non-Fernet string raises CredentialDecryptionError."""
        with pytest.raises(CredentialDecryptionError):
            decrypt_credentials("not-a-valid-fernet-token")


# ---------------------------------------------------------------------------
# Connector Model Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestConnectorModel:
    """Verify Connector catalog model invariants."""

    def test_create_connector_success(self, connector: Connector) -> None:
        """Connector creates with correct fields and string representation."""
        assert connector.name == "Web Crawler"
        assert connector.slug == "web-crawler"
        assert connector.is_active is True
        assert "Web Crawler (web_crawler)" in str(connector)

    def test_connector_slug_unique_constraint(
        self, connector: Connector, sample_config_schema: dict[str, object]
    ) -> None:
        """Duplicate slug raises error."""
        with pytest.raises(IntegrityError):
            Connector.objects.create(
                name="Duplicate Crawler",
                slug="web-crawler",
                connector_type=ConnectorType.WEB_CRAWLER,
                config_schema=sample_config_schema,
            )

    def test_connector_invalid_json_schema_fails_clean(self) -> None:
        """Invalid JSON Schema definition in config_schema fails validation."""
        invalid_schema = {"type": "invalid_type_here"}
        bad_connector = Connector(
            name="Bad Connector",
            slug="bad-connector",
            connector_type=ConnectorType.CUSTOM,
            config_schema=invalid_schema,
        )
        with pytest.raises(ValidationError):
            bad_connector.clean()


# ---------------------------------------------------------------------------
# Connection Model Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestConnectionModel:
    """Verify Connection model behavior, relations, and cascade rules."""

    def test_create_connection_with_encrypted_credentials(
        self, library: Library, connector: Connector, user: User
    ) -> None:
        """Connection stores configuration and encrypted credentials."""
        conn = Connection.objects.create(
            library=library,
            connector=connector,
            name="Docs Crawler",
            configuration={"base_url": "https://docs.example.com", "max_depth": 3},
            created_by=user,
        )
        conn.set_credentials({"api_key": "sk-prod-99999"})
        conn.save()

        conn.refresh_from_db()
        assert conn.has_credentials is True
        assert conn.get_credentials() == {"api_key": "sk-prod-99999"}
        assert "sk-prod-99999" not in conn.encrypted_credentials
        assert conn.library == library
        assert conn.connector == connector

    def test_connection_unique_name_per_library(
        self, library: Library, connector: Connector
    ) -> None:
        """Duplicate connection name in same library violates constraint."""
        Connection.objects.create(
            library=library,
            connector=connector,
            name="Primary Sync",
            configuration={"base_url": "https://docs.example.com"},
        )
        with pytest.raises(IntegrityError):
            Connection.objects.create(
                library=library,
                connector=connector,
                name="Primary Sync",
                configuration={"base_url": "https://other.example.com"},
            )

    def test_connector_deletion_protected_when_connections_exist(
        self, library: Library, connector: Connector
    ) -> None:
        """Deleting a Connector with active Connections raises ProtectedError."""
        Connection.objects.create(
            library=library,
            connector=connector,
            name="Active Conn",
            configuration={"base_url": "https://docs.example.com"},
        )
        with pytest.raises(ProtectedError):
            connector.delete()

    def test_library_deletion_cascades_connections_and_sync_jobs(
        self, library: Library, connector: Connector
    ) -> None:
        """Deleting a Library cascades its Connections and ConnectionSyncJobs."""
        conn = Connection.objects.create(
            library=library,
            connector=connector,
            name="Cascading Conn",
            configuration={"base_url": "https://docs.example.com"},
        )
        job = ConnectionSyncJob.objects.create(
            connection=conn,
            status=SyncJobStatus.COMPLETED,
            resources_created=5,
        )

        conn_id = conn.id
        job_id = job.id

        library.delete()

        assert not Connection.objects.filter(id=conn_id).exists()
        assert not ConnectionSyncJob.objects.filter(id=job_id).exists()


# ---------------------------------------------------------------------------
# ConnectionSyncJob Model Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestConnectionSyncJobModel:
    """Verify ConnectionSyncJob ledger and counters."""

    def test_create_sync_job_defaults(
        self, library: Library, connector: Connector
    ) -> None:
        """Sync job initializes with default QUEUED status and zero counters."""
        conn = Connection.objects.create(
            library=library,
            connector=connector,
            name="Test Conn",
            configuration={"base_url": "https://docs.example.com"},
        )
        job = ConnectionSyncJob.objects.create(
            connection=conn,
            celery_task_id="task-uuid-123",
        )

        assert job.status == SyncJobStatus.QUEUED
        assert job.resources_discovered == 0
        assert job.resources_created == 0
        assert job.resources_updated == 0
        assert job.resources_deleted == 0
        assert "SyncJob" in str(job)
