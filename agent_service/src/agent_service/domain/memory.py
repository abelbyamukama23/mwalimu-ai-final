"""Working context buffer and citation accumulation for an AgentRun."""

from __future__ import annotations

from dataclasses import dataclass, field

from .message import (
    EvidenceCitation,
    MessageRole,
    ModelMessage,
    ToolCallRequest,
    ToolResult,
)


@dataclass
class WorkingContextBuffer:
    """In-memory context buffer managing system prompt, history, and citations.

    Maintains the working scratchpad for the active turn and accumulates citation
    evidence returned by retrieval capabilities.
    """

    system_prompt: str = ""
    history_messages: list[ModelMessage] = field(default_factory=list)
    current_turn_messages: list[ModelMessage] = field(default_factory=list)
    _citations: list[EvidenceCitation] = field(default_factory=list)

    def add_user_message(self, content: str) -> None:
        """Append user input to the current turn."""
        self.current_turn_messages.append(
            ModelMessage(role=MessageRole.USER, content=content)
        )

    def add_assistant_message(
        self,
        content: str | None = None,
        tool_calls: list[ToolCallRequest] | None = None,
    ) -> None:
        """Append model assistant decision (text answer or tool call requests)."""
        self.current_turn_messages.append(
            ModelMessage(
                role=MessageRole.ASSISTANT,
                content=content,
                tool_calls=tool_calls,
            )
        )

    def add_tool_result(self, result: ToolResult) -> None:
        """Append tool outcome to active turn and collect citation evidence."""
        # Sanitize error or output text
        output_content = result.output if result.success else f"Error: {result.error}"
        self.current_turn_messages.append(
            ModelMessage(
                role=MessageRole.TOOL,
                content=output_content,
                tool_call_id=result.call_id,
            )
        )

        if result.citation_evidence:
            for citation in result.citation_evidence:
                if citation not in self._citations:
                    self._citations.append(citation)

    def get_messages_for_model(self) -> list[ModelMessage]:
        """Assemble the complete ordered message payload for model invocation.

        Structure:
        1. System prompt (if set)
        2. Session history messages
        3. Current turn scratchpad messages
        """
        messages: list[ModelMessage] = []
        if self.system_prompt:
            messages.append(
                ModelMessage(role=MessageRole.SYSTEM, content=self.system_prompt)
            )

        messages.extend(self.history_messages)
        messages.extend(self.current_turn_messages)
        return messages

    @property
    def citations(self) -> list[EvidenceCitation]:
        """Return accumulated citation evidence."""
        return list(self._citations)

    def estimate_token_count(self) -> int:
        """Rough heuristic token estimator (~4 chars per token)."""
        total_chars = len(self.system_prompt)
        for msg in self.history_messages + self.current_turn_messages:
            if msg.content:
                total_chars += len(msg.content)
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total_chars += len(tc.tool_name) + len(tc.arguments_json)
        return max(1, total_chars // 4)

    def prune_history_if_needed(self, max_tokens: int) -> None:
        """Prune oldest history messages in pairs (user/assistant) if exceeding budget.

        Strictly preserves system prompt and all current turn messages.
        """
        while self.history_messages and self.estimate_token_count() > max_tokens:
            # Remove oldest turn (up to 2 messages)
            self.history_messages.pop(0)
