"""AgentRun — explicit architectural concept for an agent execution.

An ``AgentRun`` represents a single invocation of the agent runtime. It
carries the ``ExecutionContext`` and any runtime identifiers needed to
correlate work with the Platform API.

Full implementation will be added during Agent Service development.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agent_service.context import ExecutionContext


class AgentRun(BaseModel):
    """A single agent execution instance.

    Attributes:
        run_id: Unique identifier for this run.
        context: Scoped execution context received from the Platform API.
    """

    run_id: str = Field(..., description="Unique run identifier")
    context: ExecutionContext
