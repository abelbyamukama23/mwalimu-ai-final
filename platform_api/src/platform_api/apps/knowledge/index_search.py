"""Back-of-book subject index search and candidate page resolution."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from platform_api.apps.processing.index_parser import normalize_index_term
from platform_api.apps.processing.models import BookIndexEntry, ProcessingStatus

from .concept_normalization import extract_query_concepts
from .policies import EffectiveRetrievalScope

from .structure_search import STOP_WORDS, _extract_ngrams, _tokenize


@dataclass(frozen=True)
class CandidatePageMatch:
    """A matched candidate page reference from a book index lookup."""

    resource_id: str
    physical_page: int
    matched_term: str


def find_candidate_index_pages(
    query: str,
    scope: EffectiveRetrievalScope,
) -> list[int]:
    """Resolve candidate document page numbers from back-of-book subject indexes in scope.

    Invariants:
    - Server-authoritative scoping: library_id and resource_id constrained.
    - Active & Ready processing run filtering.
    - Multi-concept page intersection prioritizes overlapping pages (anti-keyword-bleed).
    - Graceful fallback when no index entries match.
    """
    if not query or scope.is_empty:
        return []

    tokens = _tokenize(query)
    if not tokens:
        return []

    # Generate search phrases: full normalized query, n-grams, single non-stop tokens
    phrases: set[str] = set()
    norm_full = normalize_index_term(query)
    if norm_full:
        phrases.add(norm_full)

    for ng in _extract_ngrams(tokens):
        norm_ng = normalize_index_term(ng)
        if norm_ng:
            phrases.add(norm_ng)

    for t in tokens:
        if t not in STOP_WORDS and len(t) > 2:
            norm_t = normalize_index_term(t)
            if norm_t:
                phrases.add(norm_t)

    # 1b. Concept normalization & technical aliases
    norm_concepts = extract_query_concepts(query)
    for c in norm_concepts.canonical_concepts:
        norm_c = normalize_index_term(c)
        if norm_c:
            phrases.add(norm_c)

    for t in norm_concepts.normalized_terms:
        if t not in STOP_WORDS and len(t) > 2:
            norm_t = normalize_index_term(t)
            if norm_t:
                phrases.add(norm_t)

    if not phrases:
        return []


    # Query BookIndexEntry in authorized scope for active runs
    try:
        qs = BookIndexEntry.objects.filter(
            processing_run__is_active=True,
            processing_run__status=ProcessingStatus.READY,
            resource__library_id__in=scope.authorized_library_ids,
        )
        if scope.authorized_resource_ids is not None:
            qs = qs.filter(resource_id__in=scope.authorized_resource_ids)

        # Filter matching normalized terms
        matched_entries = list(qs.filter(normalized_term__in=phrases))

        # Also search for substring matches if exact matches were few
        if len(matched_entries) < len(phrases):
            for p in phrases:
                if len(p) >= 4 and not any(e.normalized_term == p for e in matched_entries):
                    sub_matches = list(qs.filter(normalized_term__icontains=p)[:5])
                    for sm in sub_matches:
                        if sm not in matched_entries:
                            matched_entries.append(sm)
    except Exception:
        return []

    if not matched_entries:
        return []


    # Group page sets by (resource_id, concept_phrase)
    # e.g. resource_1 -> { "reaction rate": [5,6,7,8,9], "temperature": [7,81] }
    by_resource_and_concept: dict[str, dict[str, set[int]]] = {}
    for entry in matched_entries:
        res_key = str(entry.resource_id)
        concept_dict = by_resource_and_concept.setdefault(res_key, {})
        page_set = concept_dict.setdefault(entry.normalized_term, set())
        page_set.update(entry.target_physical_pages)

    candidate_pages: list[int] = []

    for res_key, concept_dict in by_resource_and_concept.items():
        if len(concept_dict) >= 2:
            # Multi-concept intersection: pages referenced by multiple query concepts
            all_page_lists = list(concept_dict.values())
            intersection = set.intersection(*all_page_lists)
            if intersection:
                # Strong intersection found! (e.g. page 7)
                candidate_pages.extend(sorted(intersection))
                continue

            # Pairwise overlap scoring
            page_counts: Counter[int] = Counter()
            for pages in all_page_lists:
                for p in pages:
                    page_counts[p] += 1

            # Top overlapping pages
            max_count = max(page_counts.values()) if page_counts else 0
            if max_count > 1:
                top_pages = [p for p, c in page_counts.items() if c == max_count]
                candidate_pages.extend(sorted(top_pages))
                continue

        # Single concept or non-intersecting: take all matched pages
        for pages in concept_dict.values():
            candidate_pages.extend(sorted(pages))

    # Deduplicate while preserving relative order
    seen: set[int] = set()
    deduped: list[int] = []
    for p in candidate_pages:
        if p not in seen:
            seen.add(p)
            deduped.append(p)

    return deduped



def resolve_printed_page_labels_to_physical(
    resource_id: uuid.UUID,
    printed_labels: Sequence[str],
    scope: EffectiveRetrievalScope | None = None,
) -> list[int]:
    """Resolve printed page labels to physical document page numbers for an authorized resource.

    Invariants:
    - Scoped to active and ready ProcessingRun.
    - Scoped to authorized library_id and resource_id.
    - Preserves unresolvable references without fabricating false physical pages.
    """
    if not printed_labels:
        return []

    if scope is not None:
        if scope.authorized_resource_ids is not None and resource_id not in scope.authorized_resource_ids:
            return []

    from platform_api.apps.processing.models import DocumentPageMap

    norm_labels = [l.strip().lower() for l in printed_labels if l.strip()]
    if not norm_labels:
        return []

    try:
        qs = DocumentPageMap.objects.filter(
            resource_id=resource_id,
            processing_run__is_active=True,
            processing_run__status=ProcessingStatus.READY,
            normalized_label__in=norm_labels,
        )
        if scope is not None:
            qs = qs.filter(resource__library_id__in=scope.authorized_library_ids)

        return sorted({m.physical_page for m in qs})
    except Exception:
        return []

