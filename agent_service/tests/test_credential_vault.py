"""Unit tests for DelegatedCredentialVault in-memory isolation."""

import uuid

import pytest

from agent_service.infrastructure.credential_vault import DelegatedCredentialVault


def test_credential_vault_store_retrieve_and_purge() -> None:
    """Vault stores token, retrieves by run_id, and purges on demand."""
    vault = DelegatedCredentialVault()
    run_id = uuid.uuid4()
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test-payload"

    # Initially empty
    assert vault.retrieve(run_id) is None
    assert run_id not in vault

    # Store
    vault.store(run_id, token)
    assert vault.retrieve(run_id) == token
    assert run_id in vault

    # Different run ID cannot retrieve
    other_run_id = uuid.uuid4()
    assert vault.retrieve(other_run_id) is None

    # Purge
    assert vault.purge(run_id) is True
    assert vault.retrieve(run_id) is None
    assert vault.purge(run_id) is False


def test_credential_vault_empty_token_rejection() -> None:
    """Empty or None token raises ValueError."""
    vault = DelegatedCredentialVault()
    run_id = uuid.uuid4()
    with pytest.raises(ValueError, match="Token must not be empty"):
        vault.store(run_id, "")


def test_credential_vault_repr_does_not_leak_tokens() -> None:
    """Vault repr and str only report active counts, never raw tokens."""
    vault = DelegatedCredentialVault()
    run_id = uuid.uuid4()
    secret_token = "secret-token-12345"
    vault.store(run_id, secret_token)

    assert secret_token not in repr(vault)
    assert secret_token not in str(vault)
    assert "active_runs=1" in repr(vault)


def test_credential_vault_purge_all() -> None:
    """purge_all removes all active credentials."""
    vault = DelegatedCredentialVault()
    r1, r2 = uuid.uuid4(), uuid.uuid4()
    vault.store(r1, "t1")
    vault.store(r2, "t2")

    assert vault.purge_all() == 2
    assert vault.retrieve(r1) is None
    assert vault.retrieve(r2) is None
