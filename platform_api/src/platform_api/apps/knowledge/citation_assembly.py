"""Citation precision, sentence-level span pinpointing, and derivation synthesis.

This module provides deterministic tools to:
1. Extract and score sentence-level answer spans within chunks.
2. Resolve physical document pages to printed textbook page labels via DocumentPageMap.
3. Synthesize contiguous multi-chunk sequences into cohesive derivation units.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any, Sequence

from platform_api.apps.processing.models import DocumentPageMap

from .concept_normalization import extract_query_concepts
from .dto import SearchResultItemDTO
from .policies import EffectiveRetrievalScope
from .query_intent import QueryIntent, QueryIntentResult


@dataclass(frozen=True)
class EvidenceAnswerSpan:
    """An extractive sentence-level evidence span pinpointed within a chunk."""

    text: str
    char_start: int
    char_end: int
    role: str
    confidence: float


@dataclass(frozen=True)
class FormattedCitation:
    """Complete academic citation with physical-to-printed page resolution."""

    formatted: str
    printed_page: str | None
    physical_page: int | None
    section: str | None
    resource_name: str


@dataclass(frozen=True)
class SynthesizedDerivationCluster:
    """A cohesive multi-chunk derivation sequence assembled into an answer-ready unit."""

    core_chunk_id: uuid.UUID
    is_complete_derivation: bool
    formatted_citation: str
    derivation_steps: list[dict[str, Any]]
    combined_text: str


# Common abbreviations that should NOT be treated as sentence boundaries
_ABBREVIATION_PATTERN = re.compile(
    r"\b(?:e\.g|i\.e|fig|figs|dr|mr|mrs|prof|et\s+al|vs|vol|no|pp|eq|eqs)\.\s*$",
    re.IGNORECASE,
)


def split_sentences_with_offsets(text: str) -> list[tuple[str, int, int]]:
    """Split text into sentences while tracking exact character offsets.

    Invariants:
    - Preserves exact character offsets in original text.
    - Protects common academic abbreviations (e.g., i.e., Fig., et al.) and decimals.
    - Deterministic.
    """
    if not text or not text.strip():
        return []

    sentences: list[tuple[str, int, int]] = []
    # Candidate break positions: period, question mark, or exclamation mark followed by whitespace
    raw_splits = list(re.finditer(r"([.?!])(?:\s+|$)", text))

    current_start = 0
    for match in raw_splits:
        punct_end = match.end(1)
        candidate_sentence = text[current_start:punct_end]

        # Check if boundary is preceded by an abbreviation
        if _ABBREVIATION_PATTERN.search(candidate_sentence):
            continue

        # Check if period is inside a decimal number (e.g. 3.14)
        if match.group(1) == "." and match.start(1) > 0 and match.start(1) < len(text) - 1:
            prev_char = text[match.start(1) - 1]
            next_char = text[match.start(1) + 1]
            if prev_char.isdigit() and next_char.isdigit():
                continue

        # Valid sentence boundary
        clean_text = candidate_sentence.strip()
        if clean_text:
            # Adjust start for leading whitespace
            leading_ws = len(candidate_sentence) - len(candidate_sentence.lstrip())
            actual_start = current_start + leading_ws
            actual_end = actual_start + len(clean_text)
            sentences.append((clean_text, actual_start, actual_end))

        current_start = match.end()

    # Trailing sentence if any
    if current_start < len(text):
        remaining = text[current_start:].strip()
        if remaining:
            leading_ws = len(text[current_start:]) - len(text[current_start:].lstrip())
            actual_start = current_start + leading_ws
            actual_end = actual_start + len(remaining)
            sentences.append((remaining, actual_start, actual_end))

    # Fallback if no sentence boundaries matched
    if not sentences and text.strip():
        sentences.append((text.strip(), 0, len(text.strip())))

    return sentences


def extract_answer_spans(
    chunk_text: str,
    query_text: str,
    intent_result: QueryIntentResult | None,
) -> list[EvidenceAnswerSpan]:
    """Extract and classify sentence-level answer spans within a chunk.

    Invariants:
    - Zero LLM calls.
    - Deterministic.
    - Respects query intent and normalized concepts.
    """
    if not chunk_text or not query_text:
        return []

    sentence_tuples = split_sentences_with_offsets(chunk_text)
    if not sentence_tuples:
        return []

    norm_concepts = extract_query_concepts(query_text)
    key_terms: set[str] = set()
    for c in norm_concepts.canonical_concepts:
        key_terms.add(c.lower())
    for t in norm_concepts.normalized_terms:
        if len(t) >= 4 and t not in ("what", "calculate", "explain", "describe", "why"):
            key_terms.add(t.lower())

    intent = intent_result.intent if intent_result else None
    spans: list[EvidenceAnswerSpan] = []

    for s_text, start_idx, end_idx in sentence_tuples:
        s_lower = s_text.lower()
        matched_concept_count = sum(1 for kt in key_terms if kt in s_lower)
        has_concepts = matched_concept_count > 0 or not key_terms

        # 1. Definitional Intent
        if intent == QueryIntent.DEFINITIONAL:
            if re.search(r"\b(?:is|are)\s+defined\s+as\b", s_lower):
                spans.append(EvidenceAnswerSpan(
                    text=s_text,
                    char_start=start_idx,
                    char_end=end_idx,
                    role="primary_definition",
                    confidence=0.96,
                ))
            elif re.search(r"\brefers\s+to\s+(?:the|a|an)?\b", s_lower) or re.search(r"\b(?:is|are)\s+the\s+(?:minimum|total|amount|rate|measure|process|ratio)\b", s_lower):
                spans.append(EvidenceAnswerSpan(
                    text=s_text,
                    char_start=start_idx,
                    char_end=end_idx,
                    role="primary_definition",
                    confidence=0.92,
                ))
            elif re.search(r"\b(?:designated|represented|denoted)\s+by\s+(?:the\s+symbol)?\b", s_lower) or re.search(r"\bsymbol\b", s_lower):
                spans.append(EvidenceAnswerSpan(
                    text=s_text,
                    char_start=start_idx,
                    char_end=end_idx,
                    role="symbol_specification",
                    confidence=0.90,
                ))

        # 2. Quantitative Intent
        elif intent == QueryIntent.QUANTITATIVE:
            if re.search(r"\b(?:solution|therefore|result)\s*:", s_lower) or (re.search(r"\b(?:solution|therefore)\b", s_lower) and re.search(r"\b\d", s_text)):
                spans.append(EvidenceAnswerSpan(
                    text=s_text,
                    char_start=start_idx,
                    char_end=end_idx,
                    role="calculation_solution",
                    confidence=0.95,
                ))
            elif re.search(r"\b(?:given|using|substituting|values?)\b", s_lower) and re.search(r"\b\d", s_text):
                spans.append(EvidenceAnswerSpan(
                    text=s_text,
                    char_start=start_idx,
                    char_end=end_idx,
                    role="numerical_values",
                    confidence=0.89,
                ))
            elif re.search(r"\b[A-Za-z0-9_]+\s*=\s*", s_text):
                spans.append(EvidenceAnswerSpan(
                    text=s_text,
                    char_start=start_idx,
                    char_end=end_idx,
                    role="formula_definition",
                    confidence=0.94,
                ))


        # 3. Procedural Intent
        elif intent == QueryIntent.PROCEDURAL:
            if re.search(r"\bstep\s+[1-9]\b", s_lower):
                spans.append(EvidenceAnswerSpan(
                    text=s_text,
                    char_start=start_idx,
                    char_end=end_idx,
                    role="procedural_step",
                    confidence=0.95,
                ))
            elif re.search(r"\b(?:first|second|then|next|finally)\b", s_lower) and re.search(r"\b(?:measure|plot|calculate|substitute|prepare)\b", s_lower):
                spans.append(EvidenceAnswerSpan(
                    text=s_text,
                    char_start=start_idx,
                    char_end=end_idx,
                    role="procedural_step",
                    confidence=0.90,
                ))
            elif re.search(r"\b(?:solution|result)\b", s_lower):
                spans.append(EvidenceAnswerSpan(
                    text=s_text,
                    char_start=start_idx,
                    char_end=end_idx,
                    role="procedural_outcome",
                    confidence=0.92,
                ))

        # 4. Comparative Intent
        elif intent == QueryIntent.COMPARATIVE:
            if re.search(r"\b(?:whereas|while|in\s+contrast|difference\s+between|distinct\s+from)\b", s_lower):
                spans.append(EvidenceAnswerSpan(
                    text=s_text,
                    char_start=start_idx,
                    char_end=end_idx,
                    role="contrastive_statement",
                    confidence=0.95,
                ))

        # 5. Causal Intent
        elif intent == QueryIntent.CAUSAL:
            if re.search(r"\bbecause\b", s_lower) and re.search(r"\b(?:which\s+causes|leading\s+to|resulting\s+in|increases|decreases)\b", s_lower):
                spans.append(EvidenceAnswerSpan(
                    text=s_text,
                    char_start=start_idx,
                    char_end=end_idx,
                    role="causal_mechanism",
                    confidence=0.95,
                ))
            elif re.search(r"\b(?:causes|leads\s+to|results\s+in)\b", s_lower):
                spans.append(EvidenceAnswerSpan(
                    text=s_text,
                    char_start=start_idx,
                    char_end=end_idx,
                    role="causal_link",
                    confidence=0.88,
                ))

        # 6. Overview Intent
        elif intent == QueryIntent.OVERVIEW:
            if re.search(r"\b(?:in\s+this\s+chapter|this\s+section\s+covers|in\s+summary|overview|introduction)\b", s_lower):
                spans.append(EvidenceAnswerSpan(
                    text=s_text,
                    char_start=start_idx,
                    char_end=end_idx,
                    role="overview_intro",
                    confidence=0.92,
                ))

        # 7. General high-concept fallback
        elif has_concepts and matched_concept_count >= 2:
            spans.append(EvidenceAnswerSpan(
                text=s_text,
                char_start=start_idx,
                char_end=end_idx,
                role="primary_answer",
                confidence=0.85,
            ))

    # If no specific patterns matched, pick the sentence with highest concept coverage as primary
    if not spans and sentence_tuples:
        best_sentence = max(
            sentence_tuples,
            key=lambda item: sum(1 for kt in key_terms if kt in item[0].lower()),
        )
        spans.append(EvidenceAnswerSpan(
            text=best_sentence[0],
            char_start=best_sentence[1],
            char_end=best_sentence[2],
            role="primary_answer",
            confidence=0.75,
        ))

    return spans


def resolve_chunk_citations(
    chunks: Sequence[SearchResultItemDTO],
    scope: EffectiveRetrievalScope,
) -> dict[uuid.UUID, FormattedCitation]:
    """Resolve physical document pages to printed textbook citations in a single batch query.

    Invariants:
    - Zero N+1: Single batched DB query.
    - Server-authoritative scoping.
    - Active processing runs only.
    - Gracefully falls back to physical pages if DocumentPageMap is not available.
    """
    citations: dict[uuid.UUID, FormattedCitation] = {}
    if not chunks or scope.is_empty:
        return citations

    # Collect unique (resource_id, physical_page) pairs
    resource_ids: set[uuid.UUID] = set()
    physical_pages: set[int] = set()

    for item in chunks:
        res_id = item.provenance.resource_id
        resource_ids.add(res_id)
        if item.provenance.page_start is not None:
            physical_pages.add(item.provenance.page_start)
        if item.provenance.page_end is not None:
            physical_pages.add(item.provenance.page_end)

    page_map_dict: dict[tuple[uuid.UUID, int], str] = {}
    if resource_ids and physical_pages:
        try:
            qs = DocumentPageMap.objects.filter(
                resource__library_id__in=scope.authorized_library_ids,
                resource_id__in=resource_ids,
                physical_page__in=physical_pages,
                processing_run__is_active=True,
                processing_run__status="ready",
            )
            if scope.authorized_resource_ids is not None:
                qs = qs.filter(resource_id__in=scope.authorized_resource_ids)

            for pm in qs:
                page_map_dict[(pm.resource_id, pm.physical_page)] = pm.printed_label
        except Exception:
            # Fallback gracefully if database or table unavailable
            page_map_dict = {}


    # Format citations per chunk
    for item in chunks:
        prov = item.provenance
        res_id = prov.resource_id
        res_name = prov.resource_name or "Document"
        sec = prov.section
        p_start = prov.page_start
        p_end = prov.page_end

        printed_start = page_map_dict.get((res_id, p_start)) if p_start else None
        printed_end = page_map_dict.get((res_id, p_end)) if p_end else None

        page_str = ""
        printed_page_label: str | None = None

        if printed_start and printed_end and printed_start != printed_end:
            page_str = f"pp. {printed_start}–{printed_end}"
            printed_page_label = f"{printed_start}–{printed_end}"
        elif printed_start:
            page_str = f"p. {printed_start}"
            printed_page_label = printed_start
        elif p_start and p_end and p_start != p_end:
            page_str = f"pp. {p_start}–{p_end}"
            printed_page_label = f"{p_start}–{p_end}"
        elif p_start:
            page_str = f"p. {p_start}"
            printed_page_label = str(p_start)

        parts = [res_name]
        if sec:
            parts.append(sec)
        if page_str:
            parts.append(page_str)

        formatted = ", ".join(parts)
        citations[item.chunk_id] = FormattedCitation(
            formatted=formatted,
            printed_page=printed_page_label,
            physical_page=p_start,
            section=sec,
            resource_name=res_name,
        )

    return citations


def synthesize_derivation_cluster(
    cluster_items: Sequence[SearchResultItemDTO],
    query_text: str,
    intent_result: QueryIntentResult | None,
    citations_map: dict[uuid.UUID, FormattedCitation],
) -> SynthesizedDerivationCluster | None:
    """Synthesize contiguous multi-chunk sequences into a unified derivation unit."""
    if not cluster_items or len(cluster_items) < 2:
        return None

    # Verify all items share the same resource and section
    first_res = cluster_items[0].provenance.resource_id
    first_sec = cluster_items[0].provenance.section
    if not all(item.provenance.resource_id == first_res for item in cluster_items):
        return None

    sorted_items = sorted(cluster_items, key=lambda x: x.provenance.sequence)
    core_item = cluster_items[0]

    steps: list[dict[str, Any]] = []
    step_num = 1

    for item in sorted_items:
        spans = extract_answer_spans(item.text, query_text, intent_result)
        for sp in spans:
            if sp.role in ("procedural_step", "formula_definition", "numerical_values", "calculation_solution"):
                steps.append({
                    "step": step_num,
                    "role": sp.role,
                    "text": sp.text,
                    "sequence": item.provenance.sequence,
                })
                step_num += 1

    # Check if derivation contains full flow
    roles = {s["role"] for s in steps}
    has_full_flow = (
        ("formula_definition" in roles and "calculation_solution" in roles)
        or len(steps) >= 2
    )

    # Format unified citation range
    core_cit = citations_map.get(core_item.chunk_id)
    formatted_cit = core_cit.formatted if core_cit else core_item.provenance.resource_name

    combined_text = "\n\n".join(item.text for item in sorted_items)

    return SynthesizedDerivationCluster(
        core_chunk_id=core_item.chunk_id,
        is_complete_derivation=has_full_flow,
        formatted_citation=formatted_cit,
        derivation_steps=steps,
        combined_text=combined_text,
    )
