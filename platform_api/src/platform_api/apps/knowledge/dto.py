"""Data Transfer Objects for the Knowledge Gateway."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class SearchRequestDTO:
    """Request parameters for knowledge search."""

    query: str
    library_ids: list[uuid.UUID] | None = None
    resource_ids: list[uuid.UUID] | None = None
    top_k: int = 10
    similarity_threshold: float | None = None
    include_text: bool = True


@dataclass(frozen=True)
class ProvenanceDTO:
    """Complete citation provenance for a retrieved chunk."""

    resource_id: uuid.UUID
    resource_name: str
    library_id: uuid.UUID
    library_name: str
    page_start: int | None
    page_end: int | None
    section: str | None
    sequence: int
    char_start: int
    char_end: int
    content_sha256: str


@dataclass(frozen=True)
class SearchResultItemDTO:
    """A single scored chunk result with complete evidence."""

    chunk_id: uuid.UUID
    score: float
    text: str
    provenance: ProvenanceDTO


@dataclass(frozen=True)
class SearchResponseDTO:
    """Response payload containing scored results and search metadata."""

    query: str
    result_count: int
    embedding_model: str
    embedding_version: str
    results: list[SearchResultItemDTO]
    metadata: dict[str, int | float | str]
