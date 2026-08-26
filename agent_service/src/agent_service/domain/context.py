"""ExecutionContext — Immutable runtime execution context.

Encapsulates authoritative execution identity, correlation identifiers,
execution budgets, and client preferences.
Contains NO raw security credentials (credentials are isolated in the vault).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionContext:
    """Immutable domain execution context for an AgentRun.

    Attributes:
        user_id: Authoritative identifier of the invoking user.
        agent_run_id: Unique correlation identifier for this execution run.
        session_id: Conversational session/thread correlation identifier.
        max_steps: Maximum reasoning loop iterations permitted.
        timeout_seconds: Maximum total execution duration permitted.
        token_budget: Token allocation budget for context management.
        locale: User locale/language preference.
        tool_allowlist: Optional allowlist of capability names permitted.
    """

    user_id: uuid.UUID
    agent_run_id: uuid.UUID
    session_id: uuid.UUID
    max_steps: int = 10
    timeout_seconds: float = 60.0
    token_budget: int = 4000
    locale: str = "en"
    tool_allowlist: frozenset[str] | None = None

    def __post_init__(self) -> None:
        """Validate execution boundaries upon initialization."""
        if not isinstance(self.user_id, uuid.UUID):
            raise TypeError("user_id must be a valid UUID instance.")
        if not isinstance(self.agent_run_id, uuid.UUID):
            raise TypeError("agent_run_id must be a valid UUID instance.")
        if not isinstance(self.session_id, uuid.UUID):
            raise TypeError("session_id must be a valid UUID instance.")
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1.")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0.")
        if self.token_budget < 100:
            raise ValueError("token_budget must be at least 100.")

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check whether a capability is permitted under the current allowlist."""
        if self.tool_allowlist is None:
            return True
        return tool_name in self.tool_allowlist
