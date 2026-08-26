"""Server-Sent Events (SSE) formatting and data models."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

TERMINAL_SSE_EVENTS = frozenset(
    [
        "run.completed",
        "run.failed",
        "run.cancelled",
        "run.timed_out",
    ]
)


@dataclass(frozen=True)
class SSEEvent:
    """Individual Server-Sent Event compliant with the W3C EventSource standard."""

    id: int
    event: str
    data: dict[str, Any]

    def to_sse_string(self) -> str:
        """Format event as standard W3C text/event-stream line buffer."""
        payload = json.dumps(self.data, default=str)
        return f"id: {self.id}\nevent: {self.event}\ndata: {payload}\n\n"
