"""ExecutionContext — scoped context received from the Platform API.

The Agent Service never accesses PostgreSQL directly. It receives an
``ExecutionContext`` that identifies the library, user, and effective
permissions for a single agent invocation.

Full implementation will be added during Agent Service development.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ExecutionContext(BaseModel):
    """Scoped runtime context for an agent invocation.

    Attributes:
        library_id: Identifier of the library in which the agent runs.
        user_id: Identifier of the invoking user.
        permissions: Effective permissions granted for this invocation.
        metadata: Additional opaque context from the Platform API.
    """

    library_id: str = Field(..., description="Library identifier")
    user_id: str = Field(..., description="User identifier")
    permissions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
