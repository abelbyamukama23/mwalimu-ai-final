"""Unit tests for WorkingContextBuffer domain memory management."""

import uuid

from agent_service.domain.memory import WorkingContextBuffer
from agent_service.domain.message import (
    EvidenceCitation,
    MessageRole,
    ModelMessage,
    ToolCallRequest,
    ToolResult,
)


def test_working_context_buffer_message_assembly() -> None:
    """Buffer correctly stitches system prompt, history, and active turn."""
    buffer = WorkingContextBuffer(
        system_prompt="You are a biology tutor.",
        history_messages=[
            ModelMessage(role=MessageRole.USER, content="Hello"),
            ModelMessage(role=MessageRole.ASSISTANT, content="Hi! How can I help?"),
        ],
    )

    buffer.add_user_message("What is ATP?")
    tc = ToolCallRequest(
        call_id="call-1",
        tool_name="knowledge_search",
        arguments_json='{"query": "ATP function"}',
    )
    buffer.add_assistant_message(tool_calls=[tc])

    res_id = uuid.uuid4()
    lib_id = uuid.uuid4()
    citation = EvidenceCitation(
        resource_id=res_id,
        resource_name="Bio.pdf",
        library_id=lib_id,
        library_name="Main Lib",
    )
    buffer.add_tool_result(
        ToolResult(
            call_id="call-1",
            tool_name="knowledge_search",
            success=True,
            output="ATP is energy currency.",
            citation_evidence=[citation],
        )
    )

    messages = buffer.get_messages_for_model()
    assert len(messages) == 6
    assert messages[0].role == MessageRole.SYSTEM
    assert messages[0].content == "You are a biology tutor."
    assert messages[1].role == MessageRole.USER
    assert messages[1].content == "Hello"
    assert messages[2].role == MessageRole.ASSISTANT
    assert messages[3].role == MessageRole.USER
    assert messages[3].content == "What is ATP?"
    assert messages[4].role == MessageRole.ASSISTANT
    assert messages[4].tool_calls == [tc]
    assert messages[5].role == MessageRole.TOOL
    assert messages[5].content == "ATP is energy currency."

    # Citations accumulated
    assert buffer.citations == [citation]


def test_working_context_buffer_citation_deduplication() -> None:
    """Duplicate citations from multiple tool calls are deduplicated."""
    buffer = WorkingContextBuffer()
    res_id = uuid.uuid4()
    lib_id = uuid.uuid4()
    citation = EvidenceCitation(
        resource_id=res_id,
        resource_name="Bio.pdf",
        library_id=lib_id,
        library_name="Main Lib",
    )

    buffer.add_tool_result(
        ToolResult(
            call_id="c1",
            tool_name="search",
            success=True,
            output="Res 1",
            citation_evidence=[citation],
        )
    )
    buffer.add_tool_result(
        ToolResult(
            call_id="c2",
            tool_name="search",
            success=True,
            output="Res 2",
            citation_evidence=[citation],  # Same citation
        )
    )

    assert len(buffer.citations) == 1
    assert buffer.citations[0] == citation


def test_working_context_buffer_pruning() -> None:
    """History messages are pruned when exceeding token budget."""
    history = [
        ModelMessage(role=MessageRole.USER, content="A" * 400),
        ModelMessage(role=MessageRole.ASSISTANT, content="B" * 400),
        ModelMessage(role=MessageRole.USER, content="C" * 400),
        ModelMessage(role=MessageRole.ASSISTANT, content="D" * 400),
    ]
    buffer = WorkingContextBuffer(
        system_prompt="System Prompt",
        history_messages=history,
    )
    buffer.add_user_message("Latest Question")

    # Initial estimate: ~1600 chars history // 4 = ~400 tokens
    assert buffer.estimate_token_count() >= 400

    # Prune with budget of 250 tokens -> oldest messages should be removed
    buffer.prune_history_if_needed(max_tokens=250)

    # Oldest messages popped
    assert len(buffer.history_messages) < 4
    # Current turn strictly preserved
    assert len(buffer.current_turn_messages) == 1
    assert buffer.current_turn_messages[0].content == "Latest Question"
