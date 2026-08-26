"""DelegatedCredentialVault — Secure in-memory credential isolation.

Stores short-lived delegated execution tokens keyed by agent_run_id.
Tokens are injected solely into credential-aware infrastructure adapters
and purged immediately on run termination.

Tokens never appear in:
- ExecutionContext
- ModelMessage / WorkingContextBuffer
- ToolResult / ToolCallRequest
- Logging output
- API responses
"""

from __future__ import annotations

import logging
import uuid
from threading import Lock

logger = logging.getLogger(__name__)

_REDACTED = "***REDACTED***"


class DelegatedCredentialVault:
    """Thread-safe in-memory vault for delegated execution tokens.

    Keyed by agent_run_id (UUID). Each run has at most one active token.
    """

    def __init__(self) -> None:
        self._store: dict[uuid.UUID, str] = {}
        self._lock = Lock()

    def store(self, agent_run_id: uuid.UUID, token: str) -> None:
        """Store a delegated token for the given run."""
        if not token:
            raise ValueError("Token must not be empty.")
        with self._lock:
            self._store[agent_run_id] = token
        logger.debug("Credential stored for run_id=%s", agent_run_id)

    def retrieve(self, agent_run_id: uuid.UUID) -> str | None:
        """Retrieve the delegated token for a run, or None if absent."""
        with self._lock:
            return self._store.get(agent_run_id)

    def purge(self, agent_run_id: uuid.UUID) -> bool:
        """Remove the credential for a terminated run.

        Returns True if a credential was removed, False if none existed.
        """
        with self._lock:
            removed = self._store.pop(agent_run_id, None)
        if removed is not None:
            logger.debug("Credential purged for run_id=%s", agent_run_id)
            return True
        return False

    def purge_all(self) -> int:
        """Remove all stored credentials. Returns count removed."""
        with self._lock:
            count = len(self._store)
            self._store.clear()
        return count

    def __contains__(self, agent_run_id: uuid.UUID) -> bool:
        with self._lock:
            return agent_run_id in self._store

    def __repr__(self) -> str:
        with self._lock:
            count = len(self._store)
        return f"DelegatedCredentialVault(active_runs={count})"

    def __str__(self) -> str:
        return self.__repr__()
