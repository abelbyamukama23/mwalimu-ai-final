"""Deterministic reasoning engine executing the agent reasoning cycle."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from agent_service.domain.context import ExecutionContext
from agent_service.domain.memory import WorkingContextBuffer
from agent_service.domain.message import (
    MessageRole,
    ModelMessage,
    ModelResponse,
    ModelUsage,
    ToolCallRequest,
)
from agent_service.domain.protocols import ModelProviderProtocol, ToolDefinition
from agent_service.domain.run import AgentRun, RunStatus
from agent_service.infrastructure.model_gateway.errors import ModelProviderError
from agent_service.infrastructure.tool_registry import ToolRegistry

from .prompts import DEFAULT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class ReasoningLoop:
    """Orchestration engine connecting Model Gateway, Tools, and Memory."""

    def __init__(
        self,
        model_provider: ModelProviderProtocol,
        tool_registry: ToolRegistry,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_identical_tool_calls: int = 3,
    ) -> None:
        self._model_provider = model_provider
        self._tool_registry = tool_registry
        self._system_prompt = system_prompt
        self._max_identical_tool_calls = max_identical_tool_calls

    async def _invoke_model(
        self,
        messages: list[ModelMessage],
        tools: list[ToolDefinition] | None,
        cancellation_token: asyncio.Event | None,
        on_delta: Callable[[str], None] | None,
    ) -> ModelResponse:
        """Invoke the model, streaming token deltas when a delta consumer is supplied.

        When ``on_delta`` is provided the provider's streaming path is used and
        each content delta is forwarded to the consumer (which emits ``run.delta``
        SSE events). Otherwise the non-streaming path is used (e.g. tests).
        """
        if on_delta is None:
            return await self._model_provider.generate(
                messages=messages,
                tools=tools,
                cancellation_token=cancellation_token,
            )

        return await self._stream_model(
            messages=messages,
            tools=tools,
            cancellation_token=cancellation_token,
            on_delta=on_delta,
        )

    async def _stream_model(
        self,
        messages: list[ModelMessage],
        tools: list[ToolDefinition] | None,
        cancellation_token: asyncio.Event | None,
        on_delta: Callable[[str], None],
    ) -> ModelResponse:
        """Consume a streaming completion, forwarding deltas, rebuilding response."""
        content_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        current_tool_call_id: str | None = None
        current_tool_call_name = ""
        current_tool_call_arguments = ""
        finish_reason: str | None = None
        usage = ModelUsage()

        async for chunk in self._model_provider.stream_generate(
            messages=messages,
            tools=tools,
            cancellation_token=cancellation_token,
        ):
            if chunk.delta_content:
                content_parts.append(chunk.delta_content)
                on_delta(chunk.delta_content)
            if chunk.delta_tool_call:
                tc = chunk.delta_tool_call
                # Tool-call deltas arrive as partial fragments: the first fragment
                # carries the call id + tool name, later fragments carry arguments
                # with an empty id. Accumulate a single call slot and only flush
                # when a *new* non-empty call id appears.
                if tc.call_id and tc.call_id != current_tool_call_id:
                    if (
                        current_tool_call_id is not None
                        or current_tool_call_name
                        or current_tool_call_arguments
                    ):
                        tool_calls.append(
                            ToolCallRequest(
                                call_id=current_tool_call_id or "",
                                tool_name=current_tool_call_name,
                                arguments_json=current_tool_call_arguments,
                            )
                        )
                    current_tool_call_id = tc.call_id
                    current_tool_call_name = ""
                    current_tool_call_arguments = ""
                current_tool_call_name += tc.tool_name or ""
                current_tool_call_arguments += tc.arguments_json or ""
            if chunk.finish_reason:
                finish_reason = chunk.finish_reason
            if chunk.usage is not None:
                usage = chunk.usage

        if (
            current_tool_call_id is not None
            or current_tool_call_name
            or current_tool_call_arguments
        ):
            tool_calls.append(
                ToolCallRequest(
                    call_id=current_tool_call_id or "",
                    tool_name=current_tool_call_name,
                    arguments_json=current_tool_call_arguments,
                )
            )

        return ModelResponse(
            message=ModelMessage(
                role=MessageRole.ASSISTANT,
                content="".join(content_parts),
                tool_calls=tool_calls or None,
            ),
            finish_reason=finish_reason or "stop",
            usage=usage,
        )

    async def execute_run(
        self,
        run: AgentRun,
        context: ExecutionContext,
        initial_user_prompt: str,
        conversation_history: list[ModelMessage] | None = None,
        cancellation_token: asyncio.Event | None = None,
        on_delta: Callable[[str], None] | None = None,
        context_advisory: str | None = None,
        learner_adaptation: str | None = None,
    ) -> AgentRun:
        """Execute an AgentRun through the full reasoning cycle."""
        # 1. State machine transition to RUNNING
        if run.status == RunStatus.CREATED:
            run.dispatch()
            run.start()
        elif run.status == RunStatus.QUEUED:
            run.start()
        elif run.status == RunStatus.AWAITING_INPUT:
            run.provide_input()
        elif run.is_terminal:
            logger.warning(
                "Attempted to execute run %s in terminal state %s",
                run.id,
                run.status,
            )
            return run

        logger.info("run_started run_id=%s user_id=%s", run.id, context.user_id)

        # 2. Initialize working memory buffer
        # Learner adaptation is placed first so it sets the manner of teaching;
        # the core protocol + advisory that follow never allow it to override
        # factual correctness, authorization, safety, or grounding discipline.
        segments: list[str] = []
        if learner_adaptation:
            segments.append(learner_adaptation)
        segments.append(self._system_prompt)
        if context_advisory:
            segments.append(context_advisory)
        effective_system_prompt = "\n\n".join(segments)
        buffer = WorkingContextBuffer(
            system_prompt=effective_system_prompt,
            history_messages=list(conversation_history) if conversation_history else [],
        )
        buffer.add_user_message(initial_user_prompt)

        # 3. Execute with overall run timeout boundary
        try:
            await asyncio.wait_for(
                self._run_internal_loop(
                    run=run,
                    context=context,
                    buffer=buffer,
                    cancellation_token=cancellation_token,
                    on_delta=on_delta,
                ),
                timeout=context.timeout_seconds,
            )
        except TimeoutError:
            logger.warning(
                "run_timed_out run_id=%s reason=TOTAL_TIMEOUT_EXCEEDED", run.id
            )
            if not run.is_terminal:
                run.timeout(
                    "TOTAL_RUN_TIMEOUT_EXCEEDED: Exceeded total run timeout duration."
                )
        except asyncio.CancelledError:
            logger.info("run_cancelled run_id=%s", run.id)
            if not run.is_terminal:
                run.cancel()
        except Exception as exc:
            logger.error(
                "run_failed run_id=%s unexpected_error=%s", run.id, exc, exc_info=True
            )
            if not run.is_terminal:
                run.fail(
                    error_code="UNEXPECTED_RUNTIME_ERROR",
                    error_message=f"Unexpected internal engine error: {exc}",
                )

        return run

    async def _run_internal_loop(
        self,
        run: AgentRun,
        context: ExecutionContext,
        buffer: WorkingContextBuffer,
        cancellation_token: asyncio.Event | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> None:
        """Internal step iteration loop."""
        recent_tool_fingerprints: list[tuple[str, str]] = []

        while run.status == RunStatus.RUNNING:
            # Check cancellation before step
            if cancellation_token and cancellation_token.is_set():
                run.cancel()
                logger.info(
                    "run_cancelled run_id=%s at step=%d", run.id, run.step_count
                )
                break

            # Check step budget
            if run.step_count >= context.max_steps:
                run.timeout(
                    f"MAX_STEPS_EXCEEDED: Exceeded budget of {context.max_steps} steps."
                )
                logger.warning(
                    "run_timed_out run_id=%s reason=MAX_STEPS_EXCEEDED", run.id
                )
                break

            # Prune conversation history if exceeding token budget
            buffer.prune_history_if_needed(context.token_budget)

            # Get permitted tool definitions
            tool_definitions = self._tool_registry.list_definitions(context)

            # Invoke Model Gateway
            logger.debug(
                "model_call_started run_id=%s step=%d", run.id, run.step_count + 1
            )
            try:
                response = await self._invoke_model(
                    messages=buffer.get_messages_for_model(),
                    tools=tool_definitions if tool_definitions else None,
                    cancellation_token=cancellation_token,
                    on_delta=on_delta,
                )
            except ModelProviderError as exc:
                logger.error(
                    "model_call_failed run_id=%s error=%s provider=%s",
                    run.id,
                    exc,
                    exc.provider,
                )
                run.fail(error_code=exc.__class__.__name__, error_message=str(exc))
                break
            except asyncio.CancelledError:
                run.cancel()
                break

            # Record step metrics
            run.record_step(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
            )
            logger.debug(
                "model_call_completed run_id=%s prompt_tokens=%d "
                "completion_tokens=%d finish_reason=%s",
                run.id,
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
                response.finish_reason,
            )

            # Case A: Model produced final answer (no tool calls)
            if not response.message.tool_calls:
                final_answer = response.message.content or ""
                buffer.add_assistant_message(content=final_answer)
                run.complete(
                    answer=final_answer,
                    citations=buffer.citations,
                )
                total_tok = run.total_prompt_tokens + run.total_completion_tokens
                logger.info(
                    "run_completed run_id=%s steps=%d total_tokens=%d "
                    "citations_count=%d",
                    run.id,
                    run.step_count,
                    total_tok,
                    len(buffer.citations),
                )
                break

            # Case B: Model requested tool calls
            # 1. Cycle detection
            cycle_detected = False
            for tc in response.message.tool_calls:
                fp = (tc.tool_name, tc.arguments_json)
                if recent_tool_fingerprints.count(fp) >= self._max_identical_tool_calls:
                    run.fail(
                        error_code="LOOP_DETECTED",
                        error_message=(
                            f"Repeated identical tool call sequence "
                            f"detected: {tc.tool_name}"
                        ),
                    )
                    logger.warning(
                        "run_failed run_id=%s reason=LOOP_DETECTED tool=%s",
                        run.id,
                        tc.tool_name,
                    )
                    cycle_detected = True
                    break
                recent_tool_fingerprints.append(fp)

            if cycle_detected:
                break

            # 2. Add assistant decision message to memory buffer
            buffer.add_assistant_message(
                content=response.message.content,
                tool_calls=response.message.tool_calls,
            )

            # 3. Execute requested tool calls sequentially through ToolRegistry
            for tc in response.message.tool_calls:
                if cancellation_token and cancellation_token.is_set():
                    run.cancel()
                    break

                logger.debug(
                    "tool_call_started run_id=%s tool=%s call_id=%s",
                    run.id,
                    tc.tool_name,
                    tc.call_id,
                )
                tool_result = await self._tool_registry.execute(
                    request=tc,
                    context=context,
                    cancellation_token=cancellation_token,
                )
                logger.debug(
                    "tool_call_completed run_id=%s tool=%s success=%s",
                    run.id,
                    tc.tool_name,
                    tool_result.success,
                )

                if cancellation_token and cancellation_token.is_set():
                    run.cancel()
                    break

                # Append tool outcome and accumulate citations into working memory
                buffer.add_tool_result(tool_result)

            if run.status != RunStatus.RUNNING:
                break
