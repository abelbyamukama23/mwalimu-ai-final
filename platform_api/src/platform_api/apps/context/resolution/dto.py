"""Data Transfer Objects for the Mwalimu Context Resolution Engine."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from django.utils import timezone


@dataclass(frozen=True)
class ExplicitGeographicIntent:
    """Represents an explicit geographic location match detected in prompt text."""

    geographic_unit_id: uuid.UUID
    unit_name: str
    unit_type: str
    matched_text: str
    reason: str


@dataclass(frozen=True)
class ContextSignal:
    """Result of pedagogical context signal detection."""

    context_relevant: bool
    explicit_geography_detected: bool
    detected_terms: list[str]
    reason: str


@dataclass(frozen=True)
class ResolvedContextItem:
    """Individual context snippet selected by the resolver."""

    resource_id: uuid.UUID
    geographic_unit_id: uuid.UUID
    geographic_unit_name: str
    geographic_unit_type: str
    context_domain: str
    title: str
    content: str
    applicable_subjects: list[str]
    applicable_topics: list[str]
    pedagogical_purposes: list[str]
    source_type: str  # "platform" or "institution"
    selection_reason: str

    def to_dict(self) -> dict[str, Any]:
        """Convert item to dictionary for JSON serialization."""
        return {
            "resource_id": str(self.resource_id),
            "geographic_unit_id": str(self.geographic_unit_id),
            "geographic_unit_name": self.geographic_unit_name,
            "geographic_unit_type": self.geographic_unit_type,
            "context_domain": self.context_domain,
            "title": self.title,
            "content": self.content,
            "applicable_subjects": self.applicable_subjects,
            "applicable_topics": self.applicable_topics,
            "pedagogical_purposes": self.pedagogical_purposes,
            "source_type": self.source_type,
            "selection_reason": self.selection_reason,
        }


@dataclass(frozen=True)
class ResolvedContext:
    """Complete immutable structured result from ContextResolver."""

    context_considered: bool
    explicit_geographic_intent: str | None

    familiar_regions_considered: bool
    institution_regions_considered: bool

    selected_geographic_unit_ids: list[uuid.UUID]

    geographic_expansion_occurred: bool
    expansion_levels: int

    total_candidate_resources: int
    budget_limit: int

    items: list[ResolvedContextItem]

    explanation: str
    resolved_at: str

    def to_dict(self) -> dict[str, Any]:
        """Convert resolved context to dictionary for JSON serialization."""
        return {
            "context_considered": self.context_considered,
            "explicit_geographic_intent": self.explicit_geographic_intent,
            "familiar_regions_considered": self.familiar_regions_considered,
            "institution_regions_considered": self.institution_regions_considered,
            "selected_geographic_unit_ids": [
                str(uid) for uid in self.selected_geographic_unit_ids
            ],
            "geographic_expansion_occurred": self.geographic_expansion_occurred,
            "expansion_levels": self.expansion_levels,
            "total_candidate_resources": self.total_candidate_resources,
            "budget_limit": self.budget_limit,
            "items": [item.to_dict() for item in self.items],
            "explanation": self.explanation,
            "resolved_at": self.resolved_at,
        }

    @classmethod
    def empty(
        cls,
        explanation: str = "Context was not deemed pedagogically relevant.",
        budget_limit: int = 5,
    ) -> ResolvedContext:
        """Create an empty bounded ResolvedContext."""
        return cls(
            context_considered=False,
            explicit_geographic_intent=None,
            familiar_regions_considered=False,
            institution_regions_considered=False,
            selected_geographic_unit_ids=[],
            geographic_expansion_occurred=False,
            expansion_levels=0,
            total_candidate_resources=0,
            budget_limit=budget_limit,
            items=[],
            explanation=explanation,
            resolved_at=timezone.now().isoformat(),
        )
