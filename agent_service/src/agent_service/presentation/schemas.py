"""Pydantic request and response validation schemas for the Agent Service API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from agent_service.domain.message import EvidenceCitation
from agent_service.domain.run import AgentRun


class ConversationMessagePayload(BaseModel):
    """A single canonical message in the prior conversation history."""

    model_config = ConfigDict(extra="forbid")

    role: str = Field(
        pattern="^(user|assistant)$",
        description="Message author role. Strictly 'user' or 'assistant'.",
    )
    content: str = Field(
        min_length=1,
        max_length=50000,
        description="Text content of the historical message.",
    )


class ContextItemPayload(BaseModel):
    """A single resolved contextual pedagogical knowledge snippet."""

    model_config = ConfigDict(extra="forbid")

    resource_id: uuid.UUID
    geographic_unit_id: uuid.UUID
    geographic_unit_name: str
    geographic_unit_type: str
    context_domain: str
    title: str
    content: str
    applicable_subjects: list[str] = Field(default_factory=list)
    applicable_topics: list[str] = Field(default_factory=list)
    pedagogical_purposes: list[str] = Field(default_factory=list)
    source_type: str
    selection_reason: str


class ResolvedContextPayload(BaseModel):
    """Immutable resolved pedagogical context payload."""

    model_config = ConfigDict(extra="forbid")

    context_considered: bool = False
    explicit_geographic_intent: str | None = None
    familiar_regions_considered: bool = False
    institution_regions_considered: bool = False
    selected_geographic_unit_ids: list[uuid.UUID] = Field(default_factory=list)
    geographic_expansion_occurred: bool = False
    expansion_levels: int = 0
    total_candidate_resources: int = 0
    budget_limit: int = 5
    items: list[ContextItemPayload] = Field(default_factory=list)
    explanation: str = ""
    resolved_at: str = ""


class LearnerPreferencesPayload(BaseModel):
    """Persisted learner preferences forwarded for teaching adaptation.

    Preferences adapt the manner of teaching only; they never affect
    authorization, safety, grounding, or citation integrity.
    """

    model_config = ConfigDict(extra="forbid")

    pedagogical_style: str | None = None
    explanation_depth: str | None = None
    response_language: str | None = None


class CreateRunRequest(BaseModel):
    """Payload for creating and dispatching a new agent execution run."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(
        min_length=1,
        max_length=10000,
        description="The user instruction or research question.",
    )
    session_id: uuid.UUID | None = Field(
        default=None,
        description="Optional correlation session identifier. Generated if omitted.",
    )
    run_id: uuid.UUID | None = Field(
        default=None,
        description="Optional correlation run identifier. Generated if omitted.",
    )
    conversation_history: list[ConversationMessagePayload] | None = Field(
        default=None,
        max_length=50,
        description=(
            "Optional ordered prior conversation history "
            "(user/assistant) for multi-turn execution."
        ),
    )
    context: ResolvedContextPayload | None = Field(
        default=None,
        description="Optional resolved pedagogical context from Platform API.",
    )
    preferences: LearnerPreferencesPayload | None = Field(
        default=None,
        description="Optional persisted learner preferences for teaching adaptation.",
    )
    max_steps: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum reasoning steps allowed.",
    )
    timeout_seconds: float = Field(
        default=60.0,
        gt=0.0,
        le=300.0,
        description="Maximum total run execution time in seconds.",
    )
    token_budget: int = Field(
        default=4000,
        ge=100,
        le=32000,
        description="Token budget for context management.",
    )
    locale: str = Field(
        default="en",
        description="Client language or locale preference.",
    )
    tool_allowlist: list[str] | None = Field(
        default=None,
        description="Optional subset of capability names permitted for this execution.",
    )


class CitationResponse(BaseModel):
    """14-field citation evidence provenance payload."""

    model_config = ConfigDict(from_attributes=True)

    resource_id: uuid.UUID
    resource_name: str
    library_id: uuid.UUID
    library_name: str
    page_start: int | None = None
    page_end: int | None = None
    section: str | None = None
    sequence: int = 0
    char_start: int = 0
    char_end: int = 0
    content_sha256: str = ""
    chunk_id: uuid.UUID | None = None
    score: float | None = None
    title: str | None = None

    @classmethod
    def from_domain(cls, citation: EvidenceCitation) -> CitationResponse:
        """Map domain EvidenceCitation to presentation schema."""
        res_name = citation.resource_name or "Document"
        return cls(
            resource_id=citation.resource_id,
            resource_name=res_name,
            title=res_name,
            library_id=citation.library_id,
            library_name=citation.library_name,
            page_start=citation.page_start,
            page_end=citation.page_end,
            section=citation.section,
            sequence=citation.sequence,
            char_start=citation.char_start,
            char_end=citation.char_end,
            content_sha256=citation.content_sha256,
            chunk_id=citation.chunk_id,
            score=citation.score,
        )


class RunResponse(BaseModel):
    """Snapshot response model representing an AgentRun."""

    model_config = ConfigDict(from_attributes=True)

    run_id: uuid.UUID
    session_id: uuid.UUID
    status: str
    prompt: str
    answer: str | None = None
    citations: list[CitationResponse] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    step_count: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    elapsed_seconds: float = 0.0

    @classmethod
    def from_domain(cls, run: AgentRun) -> RunResponse:
        """Map domain AgentRun entity to presentation response model."""
        return cls(
            run_id=run.id,
            session_id=run.context.session_id,
            status=run.status.value,
            prompt=run.prompt,
            answer=run.answer,
            citations=[CitationResponse.from_domain(c) for c in run.citations],
            error_code=run.error_code,
            error_message=run.error_message,
            step_count=run.step_count,
            total_prompt_tokens=run.total_prompt_tokens,
            total_completion_tokens=run.total_completion_tokens,
            total_tokens=run.total_prompt_tokens + run.total_completion_tokens,
            created_at=run.created_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
            elapsed_seconds=run.elapsed_seconds,
        )


class CancelRunResponse(BaseModel):
    """Response payload confirming cancellation signal."""

    run_id: uuid.UUID
    status: str = "cancelled"
    message: str = "Run execution cancelled successfully."


class ErrorResponse(BaseModel):
    """Standardized API error response body."""

    error_code: str
    error_message: str
