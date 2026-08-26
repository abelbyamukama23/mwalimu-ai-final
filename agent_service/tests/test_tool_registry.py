"""Unit tests for ToolRegistry 5-stage pipeline."""

import asyncio
import uuid

import pytest

from agent_service.domain.context import ExecutionContext
from agent_service.domain.message import ToolCallRequest
from agent_service.infrastructure.credential_vault import DelegatedCredentialVault
from agent_service.infrastructure.tool_registry import ToolRegistry
from agent_service.infrastructure.tools.calculator import CalculatorTool
from agent_service.infrastructure.tools.knowledge_search import KnowledgeSearchTool


def _create_test_context(
    allowlist: frozenset[str] | None = None,
    timeout_seconds: float = 60.0,
) -> ExecutionContext:
    return ExecutionContext(
        user_id=uuid.uuid4(),
        agent_run_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        timeout_seconds=timeout_seconds,
        tool_allowlist=allowlist,
    )


@pytest.mark.asyncio
async def test_tool_registry_stage1_unknown_tool() -> None:
    """Stage 1: Unknown tool name returns success=False error."""
    registry = ToolRegistry([CalculatorTool()])
    ctx = _create_test_context()

    req = ToolCallRequest(
        call_id="c1",
        tool_name="nonexistent_tool",
        arguments_json='{"query": "test"}',
    )
    res = await registry.execute(req, ctx)
    assert res.success is False
    assert "Unknown tool" in (res.error or "")
    assert res.call_id == "c1"


@pytest.mark.asyncio
async def test_tool_registry_stage2_allowlist_enforcement() -> None:
    """Stage 2: Tool not in ExecutionContext.tool_allowlist is blocked."""
    calc = CalculatorTool()
    vault = DelegatedCredentialVault()
    search = KnowledgeSearchTool(credential_vault=vault)
    registry = ToolRegistry([calc, search])

    # Allowlist only permits calculator
    ctx = _create_test_context(allowlist=frozenset(["calculator"]))

    # 1. Allowed tool passes Stage 2
    req_calc = ToolCallRequest(
        call_id="c1", tool_name="calculator", arguments_json='{"expression": "2 + 2"}'
    )
    res_calc = await registry.execute(req_calc, ctx)
    assert res_calc.success is True
    assert res_calc.output == "4"

    # 2. Non-allowed tool is rejected at Stage 2
    req_search = ToolCallRequest(
        call_id="c2",
        tool_name="knowledge_search",
        arguments_json='{"query": "photosynthesis"}',
    )
    res_search = await registry.execute(req_search, ctx)
    assert res_search.success is False
    assert "not permitted for this execution" in (res_search.error or "")


@pytest.mark.asyncio
async def test_tool_registry_stage3_json_and_schema_validation() -> None:
    """Stage 3: Malformed JSON or invalid schema parameters return structured error."""
    registry = ToolRegistry([CalculatorTool()])
    ctx = _create_test_context()

    # 1. Malformed JSON
    req_bad_json = ToolCallRequest(
        call_id="c1", tool_name="calculator", arguments_json="{invalid json"
    )
    res1 = await registry.execute(req_bad_json, ctx)
    assert res1.success is False
    assert "Invalid JSON arguments" in (res1.error or "")

    # 2. Schema mismatch (missing required field)
    req_missing_field = ToolCallRequest(
        call_id="c2", tool_name="calculator", arguments_json="{}"
    )
    res2 = await registry.execute(req_missing_field, ctx)
    assert res2.success is False
    assert "Schema validation error" in (res2.error or "")

    # 3. Schema mismatch (additional prohibited properties)
    req_extra = ToolCallRequest(
        call_id="c3",
        tool_name="calculator",
        arguments_json='{"expression": "1+1", "extra": "prohibited"}',
    )
    res3 = await registry.execute(req_extra, ctx)
    assert res3.success is False
    assert "Schema validation error" in (res3.error or "")


@pytest.mark.asyncio
async def test_tool_registry_stage5_timeout_handling() -> None:
    """Stage 5: Tool exceeding execution timeout returns timed out error."""
    from agent_service.domain.protocols import ToolDefinition, ToolProtocol

    class SlowTool(ToolProtocol):
        @property
        def definition(self) -> ToolDefinition:
            return ToolDefinition(
                name="slow_tool",
                description="Slow tool",
                parameters_schema={"type": "object"},
            )

        async def execute(
            self,
            arguments: dict,
            context: ExecutionContext,
            cancellation_token: asyncio.Event | None = None,
        ):
            await asyncio.sleep(2.0)
            return None  # type: ignore

    registry = ToolRegistry([SlowTool()], default_timeout=0.1)
    ctx = _create_test_context()

    req = ToolCallRequest(call_id="c1", tool_name="slow_tool", arguments_json="{}")
    res = await registry.execute(req, ctx)
    assert res.success is False
    assert "timed out after 0.1s" in (res.error or "")


@pytest.mark.asyncio
async def test_tool_registry_cancellation_handling() -> None:
    """Stage 5: Signaled cancellation event raises asyncio.CancelledError."""
    calc = CalculatorTool()
    registry = ToolRegistry([calc])
    ctx = _create_test_context()

    token = asyncio.Event()
    token.set()  # Already cancelled

    req = ToolCallRequest(
        call_id="c1", tool_name="calculator", arguments_json='{"expression": "2+2"}'
    )
    with pytest.raises(asyncio.CancelledError):
        await registry.execute(req, ctx, cancellation_token=token)


def test_tool_registry_list_definitions_with_allowlist() -> None:
    """list_definitions filters by allowlist when ExecutionContext is supplied."""
    calc = CalculatorTool()
    vault = DelegatedCredentialVault()
    search = KnowledgeSearchTool(credential_vault=vault)
    registry = ToolRegistry([calc, search])

    # No allowlist -> all definitions returned
    assert len(registry.list_definitions()) == 2

    # Allowlist with calculator only
    ctx = _create_test_context(allowlist=frozenset(["calculator"]))
    defs = registry.list_definitions(ctx)
    assert len(defs) == 1
    assert defs[0].name == "calculator"
