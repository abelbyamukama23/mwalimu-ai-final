"""In-memory task execution and Server-Sent Events store for Agent Runs."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from typing import Any

from agent_service.domain.run import AgentRun
from agent_service.presentation.sse import SSEEvent

logger = logging.getLogger(__name__)


class InMemoryRunStore:
    """In-memory store for AgentRuns and SSE event buffers."""

    def __init__(self) -> None:
        self._runs: dict[uuid.UUID, AgentRun] = {}
        self._cancellation_tokens: dict[uuid.UUID, asyncio.Event] = {}
        self._tasks: dict[uuid.UUID, asyncio.Task[Any]] = {}
        self._event_buffers: dict[uuid.UUID, list[SSEEvent]] = {}
        self._event_counters: dict[uuid.UUID, int] = {}
        self._subscribers: dict[uuid.UUID, list[asyncio.Queue[SSEEvent]]] = {}

    def save_run(
        self,
        run: AgentRun,
        cancellation_token: asyncio.Event | None = None,
    ) -> None:
        """Register or update an AgentRun in the store."""
        self._runs[run.id] = run
        if cancellation_token is not None and run.id not in self._cancellation_tokens:
            self._cancellation_tokens[run.id] = cancellation_token
        if run.id not in self._event_buffers:
            self._event_buffers[run.id] = []
            self._event_counters[run.id] = 0
            self._subscribers[run.id] = []

    def get_run(self, run_id: uuid.UUID) -> AgentRun | None:
        """Retrieve an AgentRun by its UUID."""
        return self._runs.get(run_id)

    def get_cancellation_token(self, run_id: uuid.UUID) -> asyncio.Event | None:
        """Retrieve the cancellation event token for a run."""
        return self._cancellation_tokens.get(run_id)

    def register_task(self, run_id: uuid.UUID, task: asyncio.Task[Any]) -> None:
        """Register the running background asyncio.Task for lifecycle monitoring."""
        self._tasks[run_id] = task

    def emit_event(
        self,
        run_id: uuid.UUID,
        event_name: str,
        data: dict[str, Any],
    ) -> SSEEvent:
        """Record and broadcast an SSE event for a specific run."""
        if run_id not in self._event_counters:
            self._event_counters[run_id] = 0
            self._event_buffers[run_id] = []
            self._subscribers[run_id] = []

        self._event_counters[run_id] += 1
        seq_id = self._event_counters[run_id]

        event = SSEEvent(id=seq_id, event=event_name, data=data)
        self._event_buffers[run_id].append(event)

        # Broadcast to all live subscriber queues
        for queue in self._subscribers.get(run_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue full for run_id=%s", run_id)

        return event

    def subscribe(
        self,
        run_id: uuid.UUID,
    ) -> tuple[list[SSEEvent], asyncio.Queue[SSEEvent]]:
        """Subscribe to events for a run, returning historical buffer and live queue."""
        history = list(self._event_buffers.get(run_id, []))
        queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=500)
        if run_id in self._subscribers:
            self._subscribers[run_id].append(queue)
        else:
            self._subscribers[run_id] = [queue]
        return history, queue

    def unsubscribe(self, run_id: uuid.UUID, queue: asyncio.Queue[SSEEvent]) -> None:
        """Remove a subscriber queue upon client disconnection."""
        if run_id in self._subscribers:
            with contextlib.suppress(ValueError):
                self._subscribers[run_id].remove(queue)

    def get_events(
        self,
        run_id: uuid.UUID,
        since_id: int | None = None,
    ) -> list[SSEEvent]:
        """Get all buffered events for a run, optionally filtering by Last-Event-ID."""
        events = self._event_buffers.get(run_id, [])
        if since_id is None:
            return list(events)
        return [e for e in events if e.id > since_id]

    def clear(self) -> None:
        """Clear all in-memory runs, tasks, and event buffers."""
        self._runs.clear()
        self._cancellation_tokens.clear()
        self._tasks.clear()
        self._event_buffers.clear()
        self._event_counters.clear()
        self._subscribers.clear()


# Default singleton instance for application runtime
global_run_store = InMemoryRunStore()
