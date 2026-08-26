"""Comprehensive tests for Server-Sent Events (SSE) streaming (Phase 6.5)."""

import asyncio
import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from agent_service.domain.context import ExecutionContext
from agent_service.domain.run import AgentRun
from agent_service.infrastructure.run_store import InMemoryRunStore
from agent_service.main import app
from agent_service.presentation.sse import TERMINAL_SSE_EVENTS, SSEEvent

TEST_SECRET = "mwalimu-insecure-dev-secret-key-change-in-production"


def _mint_test_jwt(
    user_id: uuid.UUID | None = None,
    secret: str = TEST_SECRET,
) -> str:
    """Mint a Domain B JWT for SSE tests."""
    now = int(time.time())
    payload = {
        "sub": str(user_id or uuid.uuid4()),
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _mint_stream_jwt(
    user_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    secret: str = TEST_SECRET,
) -> str:
    """Mint a Domain S stream capability token for SSE tests."""
    now = int(time.time())
    payload = {
        "iss": "mwalimu-platform-api",
        "aud": "mwalimu-agent-stream",
        "sub": str(user_id or uuid.uuid4()),
        "run_id": str(run_id or uuid.uuid4()),
        "session_id": str(session_id or uuid.uuid4()),
        "scope": "run:stream",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# SSEEvent Model Tests
# ---------------------------------------------------------------------------


class TestSSEEvent:
    """Verify SSEEvent data model and W3C serialization."""

    def test_sse_event_to_string_format(self) -> None:
        """SSE output conforms to W3C text/event-stream format."""
        event = SSEEvent(
            id=1,
            event="run.started",
            data={"run_id": "abc123", "status": "running"},
        )
        sse_str = event.to_sse_string()
        assert sse_str.startswith("id: 1\n")
        assert "event: run.started\n" in sse_str
        assert "data: " in sse_str
        assert sse_str.endswith("\n\n")

    def test_sse_event_frozen(self) -> None:
        """SSEEvent is a frozen dataclass."""
        event = SSEEvent(id=1, event="run.started", data={})
        with pytest.raises(AttributeError):
            event.id = 2  # type: ignore[misc]

    def test_terminal_events_defined(self) -> None:
        """All terminal SSE event names are accounted for."""
        assert "run.completed" in TERMINAL_SSE_EVENTS
        assert "run.failed" in TERMINAL_SSE_EVENTS
        assert "run.cancelled" in TERMINAL_SSE_EVENTS
        assert "run.timed_out" in TERMINAL_SSE_EVENTS
        assert len(TERMINAL_SSE_EVENTS) == 4


# ---------------------------------------------------------------------------
# InMemoryRunStore SSE Tests
# ---------------------------------------------------------------------------


class TestRunStoreSSEEvents:
    """Verify InMemoryRunStore event emission, buffering, and subscription."""

    def setup_method(self) -> None:
        self.store = InMemoryRunStore()
        self.run_id = uuid.uuid4()
        context = ExecutionContext(
            user_id=uuid.uuid4(),
            agent_run_id=self.run_id,
            session_id=uuid.uuid4(),
        )
        run = AgentRun(id=self.run_id, context=context, prompt="test")
        self.store.save_run(run)

    def test_emit_event_increments_sequence(self) -> None:
        """Event IDs are sequential starting from 1."""
        e1 = self.store.emit_event(
            self.run_id, "run.created", {"run_id": str(self.run_id)}
        )
        e2 = self.store.emit_event(
            self.run_id, "run.started", {"run_id": str(self.run_id)}
        )
        assert e1.id == 1
        assert e2.id == 2

    def test_get_events_returns_all(self) -> None:
        """get_events without since_id returns all buffered events."""
        self.store.emit_event(self.run_id, "run.created", {"run_id": str(self.run_id)})
        self.store.emit_event(self.run_id, "run.started", {"run_id": str(self.run_id)})
        events = self.store.get_events(self.run_id)
        assert len(events) == 2

    def test_get_events_with_since_id_filters(self) -> None:
        """get_events with since_id returns only events after that ID."""
        self.store.emit_event(self.run_id, "run.created", {"run_id": str(self.run_id)})
        self.store.emit_event(self.run_id, "run.started", {"run_id": str(self.run_id)})
        self.store.emit_event(
            self.run_id, "step.started", {"run_id": str(self.run_id), "step": 1}
        )
        events = self.store.get_events(self.run_id, since_id=1)
        assert len(events) == 2
        assert events[0].id == 2
        assert events[1].id == 3

    def test_subscribe_gets_history_and_queue(self) -> None:
        """subscribe() returns existing history and a live queue."""
        self.store.emit_event(self.run_id, "run.created", {"run_id": str(self.run_id)})
        history, queue = self.store.subscribe(self.run_id)
        assert len(history) == 1
        assert history[0].event == "run.created"
        assert isinstance(queue, asyncio.Queue)

    @pytest.mark.asyncio
    async def test_live_events_broadcast_to_subscribers(self) -> None:
        """Events emitted after subscribe are available in the queue."""
        _, queue = self.store.subscribe(self.run_id)
        self.store.emit_event(self.run_id, "run.started", {"run_id": str(self.run_id)})
        event = queue.get_nowait()
        assert event.event == "run.started"

    def test_unsubscribe_removes_queue(self) -> None:
        """After unsubscribe, queue no longer receives events."""
        _, queue = self.store.subscribe(self.run_id)
        self.store.unsubscribe(self.run_id, queue)
        self.store.emit_event(self.run_id, "run.started", {"run_id": str(self.run_id)})
        assert queue.empty()

    def test_get_events_for_unknown_run(self) -> None:
        """get_events for non-existent run returns empty list."""
        events = self.store.get_events(uuid.uuid4())
        assert events == []

    def test_clear_removes_all(self) -> None:
        """clear() removes all runs and event buffers."""
        self.store.emit_event(self.run_id, "run.created", {"run_id": str(self.run_id)})
        self.store.clear()
        assert self.store.get_run(self.run_id) is None
        assert self.store.get_events(self.run_id) == []


# ---------------------------------------------------------------------------
# SSE Event Taxonomy Tests
# ---------------------------------------------------------------------------


class TestSSEEventTaxonomy:
    """Verify correct event lifecycle progression and naming."""

    def setup_method(self) -> None:
        self.store = InMemoryRunStore()
        self.run_id = uuid.uuid4()
        context = ExecutionContext(
            user_id=uuid.uuid4(),
            agent_run_id=self.run_id,
            session_id=uuid.uuid4(),
        )
        run = AgentRun(id=self.run_id, context=context, prompt="test")
        self.store.save_run(run)

    def test_full_lifecycle_event_sequence(self) -> None:
        """Events follow expected ordering for a successful run."""
        events_emitted: list[tuple[str, dict[str, object]]] = [
            ("run.created", {"run_id": str(self.run_id), "status": "queued"}),
            ("run.started", {"run_id": str(self.run_id), "status": "running"}),
            ("step.started", {"run_id": str(self.run_id), "step": 1}),
            (
                "model.delta",
                {
                    "run_id": str(self.run_id),
                    "step": 1,
                    "delta_content": "Hello ",
                },
            ),
            (
                "model.delta",
                {
                    "run_id": str(self.run_id),
                    "step": 1,
                    "delta_content": "world",
                },
            ),
            (
                "tool.started",
                {
                    "run_id": str(self.run_id),
                    "step": 1,
                    "tool_name": "calculator",
                    "call_id": "c1",
                },
            ),
            (
                "tool.completed",
                {
                    "run_id": str(self.run_id),
                    "step": 1,
                    "tool_name": "calculator",
                    "call_id": "c1",
                    "success": True,
                },
            ),
            (
                "run.completed",
                {
                    "run_id": str(self.run_id),
                    "status": "completed",
                    "answer": "Hello world. 42.",
                    "total_tokens": 25,
                },
            ),
        ]

        for event_name, data in events_emitted:
            self.store.emit_event(self.run_id, event_name, data)

        all_events = self.store.get_events(self.run_id)
        assert len(all_events) == 8
        assert all_events[0].event == "run.created"
        assert all_events[1].event == "run.started"
        assert all_events[2].event == "step.started"
        assert all_events[3].event == "model.delta"
        assert all_events[4].event == "model.delta"
        assert all_events[5].event == "tool.started"
        assert all_events[6].event == "tool.completed"
        assert all_events[7].event == "run.completed"

    def test_no_credential_leakage_in_events(self) -> None:
        """No event payload contains delegated credentials or tokens."""
        events_to_check: list[tuple[str, dict[str, object]]] = [
            (
                "run.created",
                {"run_id": str(self.run_id), "session_id": str(uuid.uuid4())},
            ),
            ("run.started", {"run_id": str(self.run_id)}),
            (
                "run.completed",
                {
                    "run_id": str(self.run_id),
                    "answer": "result",
                    "total_tokens": 10,
                },
            ),
        ]

        for event_name, data in events_to_check:
            event = self.store.emit_event(self.run_id, event_name, data)
            sse_str = event.to_sse_string()
            assert "delegated_token" not in sse_str
            assert "DELEGATION_SIGNING_KEY" not in sse_str
            assert "api_key" not in sse_str.lower()

    def test_failed_run_event(self) -> None:
        """run.failed event includes error_code and error_message."""
        event = self.store.emit_event(
            self.run_id,
            "run.failed",
            {
                "run_id": str(self.run_id),
                "status": "failed",
                "error_code": "MODEL_ERROR",
                "error_message": "Provider timeout",
            },
        )
        assert event.event == "run.failed"
        assert event.data["error_code"] == "MODEL_ERROR"

    def test_cancelled_run_event(self) -> None:
        """run.cancelled event is well-formed."""
        event = self.store.emit_event(
            self.run_id,
            "run.cancelled",
            {"run_id": str(self.run_id), "status": "cancelled"},
        )
        assert event.event == "run.cancelled"

    def test_timed_out_run_event(self) -> None:
        """run.timed_out event includes error_message."""
        event = self.store.emit_event(
            self.run_id,
            "run.timed_out",
            {
                "run_id": str(self.run_id),
                "status": "timed_out",
                "error_message": "Budget exceeded",
            },
        )
        assert event.event == "run.timed_out"
        assert event.data["error_message"] == "Budget exceeded"


# ---------------------------------------------------------------------------
# SSE Streaming Endpoint Tests (via TestClient)
# ---------------------------------------------------------------------------


class TestSSEStreamingEndpoint:
    """Verify SSE streaming endpoint behavior."""

    def _setup_store_with_completed_run(
        self,
    ) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, InMemoryRunStore]:
        """Create a store with a run that has completed events."""
        from agent_service.infrastructure.run_store import global_run_store

        global_run_store.clear()
        user_id = uuid.uuid4()
        run_id = uuid.uuid4()
        session_id = uuid.uuid4()
        context = ExecutionContext(
            user_id=user_id,
            agent_run_id=run_id,
            session_id=session_id,
        )
        run = AgentRun(id=run_id, context=context, prompt="test")
        run.dispatch()
        global_run_store.save_run(run)
        global_run_store.emit_event(
            run_id, "run.created", {"run_id": str(run_id), "status": "queued"}
        )
        global_run_store.emit_event(
            run_id,
            "run.started",
            {"run_id": str(run_id), "status": "running"},
        )
        global_run_store.emit_event(
            run_id,
            "run.completed",
            {
                "run_id": str(run_id),
                "status": "completed",
                "answer": "Done",
                "total_tokens": 10,
            },
        )
        return user_id, run_id, session_id, global_run_store

    def test_sse_endpoint_no_auth_returns_401(self) -> None:
        """SSE endpoint without auth returns 401."""
        from agent_service.infrastructure.run_store import global_run_store

        global_run_store.clear()
        with TestClient(app) as client:
            resp = client.get(f"/api/v1/runs/{uuid.uuid4()}/events")
        assert resp.status_code in (401, 403)

    def test_sse_endpoint_nonexistent_run_returns_404(self) -> None:
        """SSE endpoint for nonexistent run returns 404."""
        from agent_service.infrastructure.run_store import global_run_store

        global_run_store.clear()
        run_id = uuid.uuid4()
        token = _mint_stream_jwt(run_id=run_id)
        with TestClient(app) as client:
            resp = client.get(
                f"/api/v1/runs/{run_id}/events",
                headers=_auth_header(token),
            )
        assert resp.status_code == 404

    def test_sse_endpoint_user_isolation(self) -> None:
        """User B cannot subscribe to User A's run events."""
        user_a, run_id, session_id, _ = self._setup_store_with_completed_run()
        user_b = uuid.uuid4()
        token_b = _mint_stream_jwt(user_id=user_b, run_id=run_id, session_id=session_id)
        with TestClient(app) as client:
            resp = client.get(
                f"/api/v1/runs/{run_id}/events",
                headers=_auth_header(token_b),
            )
        assert resp.status_code == 404

    def test_sse_endpoint_replays_completed_run(self) -> None:
        """SSE endpoint replays all events for a completed run."""
        user_id, run_id, session_id, _ = self._setup_store_with_completed_run()
        token = _mint_stream_jwt(user_id=user_id, run_id=run_id, session_id=session_id)
        with TestClient(app) as client:
            resp = client.get(
                f"/api/v1/runs/{run_id}/events",
                headers=_auth_header(token),
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        body = resp.text
        assert "event: run.created" in body
        assert "event: run.started" in body
        assert "event: run.completed" in body

    def test_sse_last_event_id_resumption(self) -> None:
        """Reconnection with Last-Event-ID skips prior events."""
        user_id, run_id, session_id, _ = self._setup_store_with_completed_run()
        token = _mint_stream_jwt(user_id=user_id, run_id=run_id, session_id=session_id)
        with TestClient(app) as client:
            resp = client.get(
                f"/api/v1/runs/{run_id}/events",
                headers={**_auth_header(token), "Last-Event-ID": "2"},
            )
        assert resp.status_code == 200
        body = resp.text
        # Event 1 (run.created) and Event 2 (run.started) should be skipped
        assert "event: run.created" not in body
        assert "event: run.started" not in body
        # Event 3 (run.completed) should still be present
        assert "event: run.completed" in body

    def test_sse_no_credential_leakage_in_stream(self) -> None:
        """No credentials appear in the SSE stream body."""
        user_id, run_id, session_id, _ = self._setup_store_with_completed_run()
        token = _mint_stream_jwt(user_id=user_id, run_id=run_id, session_id=session_id)
        with TestClient(app) as client:
            resp = client.get(
                f"/api/v1/runs/{run_id}/events",
                headers=_auth_header(token),
            )
        body = resp.text
        assert "delegated_token" not in body
        assert "api_key" not in body.lower()
