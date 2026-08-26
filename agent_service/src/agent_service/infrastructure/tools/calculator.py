"""Safe arithmetic calculator native capability using AST evaluation.

Strictly evaluates mathematical arithmetic expressions without eval() or exec().
Prohibits function calls, variable lookups, imports, and arbitrary code execution.
"""

from __future__ import annotations

import ast
import asyncio
import operator
from collections.abc import Callable
from typing import Any, cast

from agent_service.domain.context import ExecutionContext
from agent_service.domain.message import ToolResult
from agent_service.domain.protocols import ToolDefinition, ToolProtocol

# Permitted binary operators
_SAFE_BINARY_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

# Permitted unary operators
_SAFE_UNARY_OPS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

MAX_EXPONENT = 1000
MAX_EXPRESSION_LENGTH = 500


class SafeArithmeticEvaluator(ast.NodeVisitor):
    """AST visitor that strictly evaluates arithmetic nodes."""

    def visit(self, node: ast.AST) -> float | int:
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return cast(float | int, visitor(node))

    def generic_visit(self, node: ast.AST) -> Any:
        raise ValueError(
            f"Unsupported syntax or expression element: {type(node).__name__}"
        )

    def visit_Expression(self, node: ast.Expression) -> float | int:  # noqa: N802
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> float | int:  # noqa: N802
        if isinstance(node.value, int | float) and not isinstance(node.value, bool):
            return node.value
        raise ValueError(f"Unsupported literal value type: {type(node.value).__name__}")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> float | int:  # noqa: N802
        op_type = type(node.op)
        if op_type not in _SAFE_UNARY_OPS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        operand = self.visit(node.operand)
        return cast(float | int, _SAFE_UNARY_OPS[op_type](operand))

    def visit_BinOp(self, node: ast.BinOp) -> float | int:  # noqa: N802
        op_type = type(node.op)
        if op_type not in _SAFE_BINARY_OPS:
            raise ValueError(f"Unsupported binary operator: {op_type.__name__}")

        left = self.visit(node.left)
        right = self.visit(node.right)

        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Division by zero.")

        if op_type is ast.Pow:
            if abs(right) > MAX_EXPONENT:
                raise ValueError(
                    f"Exponent exceeds maximum allowed limit ({MAX_EXPONENT})."
                )
            if abs(left) > 1 and right > 100:
                # Prevent overflow or extreme CPU memory allocation
                raise ValueError("Exponent calculation exceeds safety limits.")

        return cast(float | int, _SAFE_BINARY_OPS[op_type](left, right))


def evaluate_expression(expr: str) -> float | int:
    """Safely parse and evaluate a mathematical expression."""
    cleaned = expr.strip()
    if not cleaned:
        raise ValueError("Empty expression.")
    if len(cleaned) > MAX_EXPRESSION_LENGTH:
        raise ValueError(
            f"Expression exceeds maximum length of {MAX_EXPRESSION_LENGTH} characters."
        )

    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid arithmetic expression syntax: {exc.msg}") from exc

    evaluator = SafeArithmeticEvaluator()
    return evaluator.visit(tree)


class CalculatorTool(ToolProtocol):
    """Native in-process tool for safe arithmetic computations."""

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="calculator",
            description=(
                "Perform safe basic arithmetic calculations "
                "(addition, subtraction, multiplication, division, modulo, power)."
            ),
            parameters_schema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": (
                            "Mathematical expression (e.g., '15 * (4 + 8) / 2')."
                        ),
                    },
                },
                "required": ["expression"],
                "additionalProperties": False,
            },
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ExecutionContext,
        cancellation_token: asyncio.Event | None = None,
    ) -> ToolResult:
        if cancellation_token and cancellation_token.is_set():
            raise asyncio.CancelledError("Calculator execution cancelled.")

        expression = arguments.get("expression")
        if not isinstance(expression, str):
            return ToolResult(
                call_id="",
                tool_name=self.definition.name,
                success=False,
                output="",
                error="Parameter 'expression' must be a string.",
            )

        try:
            result = evaluate_expression(expression)
            # Format nicely (int if whole number, float otherwise)
            if isinstance(result, float) and result.is_integer():
                formatted_output = str(int(result))
            else:
                formatted_output = str(result)

            return ToolResult(
                call_id="",
                tool_name=self.definition.name,
                success=True,
                output=formatted_output,
            )
        except ZeroDivisionError as exc:
            return ToolResult(
                call_id="",
                tool_name=self.definition.name,
                success=False,
                output="",
                error=f"Calculation error: {exc}",
            )
        except ValueError as exc:
            return ToolResult(
                call_id="",
                tool_name=self.definition.name,
                success=False,
                output="",
                error=f"Invalid expression: {exc}",
            )
        except Exception as exc:
            return ToolResult(
                call_id="",
                tool_name=self.definition.name,
                success=False,
                output="",
                error=f"Unexpected calculation error: {exc}",
            )
