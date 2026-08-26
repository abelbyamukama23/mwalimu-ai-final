"""FastAPI presentation routes for Agent Service runs and SSE streaming."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from agent_service.application.reasoning_loop import ReasoningLoop
from agent_service.application.use_cases import (
    CancelRunUseCase,
    GetRunStatusUseCase,
    RunAgentUseCase,
    RunNotFoundError,
)
from agent_service.infrastructure.credential_vault import DelegatedCredentialVault
from agent_service.infrastructure.model_gateway.factory import get_model_provider
from agent_service.infrastructure.run_store import InMemoryRunStore, global_run_store
from agent_service.infrastructure.tool_registry import ToolRegistry
from agent_service.infrastructure.tools.calculator import CalculatorTool
from agent_service.infrastructure.tools.knowledge_search import KnowledgeSearchTool
from agent_service.presentation.schemas import (
    CancelRunResponse,
    CreateRunRequest,
    RunResponse,
)
from agent_service.presentation.security import (
    AuthenticatedPrincipal,
    StreamingPrincipal,
    get_authenticated_principal,
    get_streaming_principal,
)
from agent_service.presentation.sse import TERMINAL_SSE_EVENTS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/runs", tags=["Agent Runs"])


global_credential_vault = DelegatedCredentialVault()


def get_default_tool_registry(
    vault: DelegatedCredentialVault | None = None,
) -> ToolRegistry:
    """Create standard ToolRegistry populated with native and gateway capabilities."""
    v = vault or global_credential_vault
    calc = CalculatorTool()
    knowledge = KnowledgeSearchTool(credential_vault=v)
    return ToolRegistry([calc, knowledge])


def get_default_reasoning_loop(
    registry: ToolRegistry | None = None,
) -> ReasoningLoop:
    """Create default ReasoningLoop using configured ModelProvider and ToolRegistry."""
    provider = get_model_provider()
    reg = registry or get_default_tool_registry()
    return ReasoningLoop(model_provider=provider, tool_registry=reg)


async def sse_event_stream(
    run_id: uuid.UUID,
    run_store: InMemoryRunStore,
    last_event_id: int | None = None,
) -> AsyncIterator[str]:
    """Asynchronous generator streaming SSE event strings for a run."""
    history, queue = run_store.subscribe(run_id)
    try:
        # 1. Replay historical buffered events
        for event in history:
            if last_event_id is not None and event.id <= last_event_id:
                continue
            yield event.to_sse_string()
            if event.event in TERMINAL_SSE_EVENTS:
                return

        # 2. Stream live events as they occur
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield event.to_sse_string()
                if event.event in TERMINAL_SSE_EVENTS:
                    break
            except TimeoutError:
                # Keep-alive SSE comment to prevent connection drop
                yield ": keep-alive\n\n"
    finally:
        run_store.unsubscribe(run_id, queue)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RunResponse,
    summary="Create and dispatch an agent run",
)
async def create_run(
    request: CreateRunRequest,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(get_authenticated_principal),
    ],
    x_delegated_token: Annotated[
        str | None,
        Header(alias="X-Delegated-Token"),
    ] = None,
) -> RunResponse:
    """Create an AgentRun, schedule background task, and return metadata."""
    vault = global_credential_vault
    registry = get_default_tool_registry(vault)
    loop = get_default_reasoning_loop(registry)
    use_case = RunAgentUseCase(
        reasoning_loop=loop,
        tool_registry=registry,
        run_store=global_run_store,
        credential_vault=vault,
    )
    run = await use_case.execute(principal=principal, request=request)
    if x_delegated_token:
        vault.store(run.id, x_delegated_token)
    return RunResponse.from_domain(run)


@router.get(
    "/{run_id}",
    response_model=RunResponse,
    summary="Retrieve snapshot status of an agent run",
)
async def get_run_status(
    run_id: uuid.UUID,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(get_authenticated_principal),
    ],
) -> RunResponse:
    """Retrieve run execution snapshot with answers, metrics, and citations."""
    use_case = GetRunStatusUseCase(run_store=global_run_store)
    try:
        run = use_case.execute(principal=principal, run_id=run_id)
    except RunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found.",
        ) from exc
    return RunResponse.from_domain(run)


@router.post(
    "/{run_id}/cancel",
    response_model=CancelRunResponse,
    summary="Cancel an active agent run",
)
async def cancel_run(
    run_id: uuid.UUID,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(get_authenticated_principal),
    ],
) -> CancelRunResponse:
    """Signal cooperative cancellation for an active run."""
    use_case = CancelRunUseCase(run_store=global_run_store)
    try:
        run = use_case.execute(principal=principal, run_id=run_id)
    except RunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found.",
        ) from exc
    return CancelRunResponse(run_id=run.id, status="cancelled")


@router.get(
    "/{run_id}/events",
    summary="Subscribe to Server-Sent Events (SSE) for a run",
)
async def stream_run_events(
    run_id: uuid.UUID,
    principal: Annotated[
        StreamingPrincipal,
        Depends(get_streaming_principal),
    ],
    last_event_id: Annotated[
        str | None,
        Header(alias="Last-Event-ID"),
    ] = None,
) -> StreamingResponse:
    """Stream real-time execution observations via W3C standard SSE.

    Requires a Domain S stream capability token with:
    - ticket.run_id == path run_id
    - ticket.sub == local run owner (user_id)
    """
    # 1. Verify ticket run_id matches URL path run_id
    if principal.run_id != run_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Streaming ticket is not authorized for this run.",
        )

    # 2. Verify run exists locally and ticket sub matches run owner
    run = global_run_store.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found.",
        )
    if run.context.user_id != principal.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found.",
        )

    since_id: int | None = None
    if last_event_id is not None:
        with contextlib.suppress(ValueError):
            since_id = int(last_event_id)

    return StreamingResponse(
        sse_event_stream(
            run_id=run_id,
            run_store=global_run_store,
            last_event_id=since_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
