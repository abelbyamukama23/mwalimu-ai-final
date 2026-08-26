"""Unit tests for CalculatorTool and safe AST arithmetic evaluation."""

import uuid

import pytest

from agent_service.domain.context import ExecutionContext
from agent_service.infrastructure.tools.calculator import (
    CalculatorTool,
    evaluate_expression,
)


def _create_test_context() -> ExecutionContext:
    return ExecutionContext(
        user_id=uuid.uuid4(),
        agent_run_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )


def test_evaluate_expression_basic_arithmetic() -> None:
    """Basic arithmetic operations evaluate correctly."""
    assert evaluate_expression("2 + 3") == 5
    assert evaluate_expression("10 - 4") == 6
    assert evaluate_expression("6 * 7") == 42
    assert evaluate_expression("20 / 4") == 5.0
    assert evaluate_expression("21 // 4") == 5
    assert evaluate_expression("21 % 4") == 1
    assert evaluate_expression("2 ** 8") == 256


def test_evaluate_expression_precedence_and_grouping() -> None:
    """Operator precedence and parentheses are strictly respected."""
    assert evaluate_expression("2 + 3 * 4") == 14
    assert evaluate_expression("(2 + 3) * 4") == 20
    assert evaluate_expression("100 / (2 + 3 * 6)") == 5.0
    assert evaluate_expression("-5 + 10") == 5
    assert evaluate_expression("+5 * -2") == -10


def test_evaluate_expression_division_by_zero() -> None:
    """Division or modulo by zero raises ZeroDivisionError."""
    with pytest.raises(ZeroDivisionError, match="Division by zero"):
        evaluate_expression("10 / 0")
    with pytest.raises(ZeroDivisionError, match="Division by zero"):
        evaluate_expression("10 // 0")
    with pytest.raises(ZeroDivisionError, match="Division by zero"):
        evaluate_expression("10 % 0")


def test_evaluate_expression_security_prohibited_nodes() -> None:
    """Attempts to call functions, access variables, or execute code are rejected."""
    prohibited = [
        "__import__('os').system('ls')",
        "eval('2 + 2')",
        "exec('x = 1')",
        "abs(-5)",
        "open('/etc/passwd')",
        "x + 1",
        "[x for x in range(10)]",
        "'hello' + 'world'",
        "True + 1",
    ]
    for expr in prohibited:
        with pytest.raises(ValueError):
            evaluate_expression(expr)


def test_evaluate_expression_exponent_limit() -> None:
    """Excessive exponents are rejected to prevent CPU/memory exhaustion."""
    with pytest.raises(ValueError, match="Exponent calculation exceeds safety limits"):
        evaluate_expression("2 ** 1000")


@pytest.mark.asyncio
async def test_calculator_tool_execute_success() -> None:
    """CalculatorTool returns successful ToolResult for valid arithmetic."""
    tool = CalculatorTool()
    ctx = _create_test_context()

    res = await tool.execute(arguments={"expression": "12 * (3 + 4)"}, context=ctx)
    assert res.success is True
    assert res.output == "84"
    assert res.error is None


@pytest.mark.asyncio
async def test_calculator_tool_execute_errors() -> None:
    """CalculatorTool safely handles division by zero and invalid syntax."""
    tool = CalculatorTool()
    ctx = _create_test_context()

    # Division by zero
    res1 = await tool.execute(arguments={"expression": "10 / 0"}, context=ctx)
    assert res1.success is False
    assert "Division by zero" in (res1.error or "")

    # Malicious/invalid expression
    res2 = await tool.execute(arguments={"expression": "import os"}, context=ctx)
    assert res2.success is False
    assert "Invalid expression" in (res2.error or "")
