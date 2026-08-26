"""Agent Service Domain Layer.

Contains core entities, value objects, state machines, and protocols.
Strictly decoupled from presentation, infrastructure, and third-party SDKs.
"""

from .context import ExecutionContext
from .memory import WorkingContextBuffer
from .message import (
    EvidenceCitation,
    MessageRole,
    ModelMessage,
    ModelResponse,
    ModelStreamChunk,
    ModelUsage,
    ToolCallRequest,
    ToolResult,
)
from .protocols import ModelProviderProtocol, ToolDefinition, ToolProtocol
from .run import AgentRun, InvalidStateTransitionError, RunStatus

__all__ = [
    "AgentRun",
    "EvidenceCitation",
    "ExecutionContext",
    "InvalidStateTransitionError",
    "MessageRole",
    "ModelMessage",
    "ModelProviderProtocol",
    "ModelResponse",
    "ModelStreamChunk",
    "ModelUsage",
    "RunStatus",
    "ToolCallRequest",
    "ToolDefinition",
    "ToolProtocol",
    "ToolResult",
    "WorkingContextBuffer",
]
