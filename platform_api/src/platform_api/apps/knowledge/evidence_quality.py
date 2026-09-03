"""Evidence quality evaluation and answer-readiness scoring for knowledge retrieval.

This module provides deterministic, in-memory evidence evaluation to distinguish between
merely 'relevant' passages and 'answer-ready' evidence for a learner's question.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Sequence

from .concept_normalization import extract_query_concepts
from .dto import SearchResultItemDTO
from .query_intent import QueryIntent, QueryIntentResult


@dataclass(frozen=True)
class EvidenceQuality:
    """Deterministic assessment of a retrieved passage's answer readiness."""

    directness: float           # 0.0 to 1.0 (directly addresses query concept)
    completeness: float         # 0.0 to 1.0 (sufficiency of evidence)
    intent_alignment: float     # 0.0 to 1.0 (matches query intent requirements)
    concept_coverage: float     # 0.0 to 1.0 (fraction of key query concepts present)
    answer_marker_score: float  # 0.0 to 1.0 (presence of answer markers)
    structural_authority: float # 0.0 to 1.0 (heading / level / position authority)
    quality_score: float        # Composite evidence quality in [0.0, 1.0]
    evidence_bonus: float       # Bounded bonus in [0.0, 0.08]
    reasons: tuple[str, ...]    # Explainable evidence markers found


@dataclass(frozen=True)
class ClusterEvidenceQuality:
    """Assessment of an expanded contiguous sequence cluster."""

    core_chunk_id: uuid.UUID
    cluster_size: int
    is_answer_ready: bool
    cluster_score: float
    combined_concept_coverage: float
    reasons: tuple[str, ...]


# Direct definition markers
_DEFINITIONAL_DIRECT_PATTERNS = [
    re.compile(r"\b(?:is|are)\s+defined\s+as\b", re.IGNORECASE),
    re.compile(r"\b(?:can\s+be|is)\s+defined\s+to\s+be\b", re.IGNORECASE),
    re.compile(r"\brefers\s+to\s+(?:the|a|an)?\b", re.IGNORECASE),
    re.compile(r"\b(?:is|are)\s+the\s+(?:minimum|total|amount|rate|measure|process|ratio)\b", re.IGNORECASE),
    re.compile(r"\bmeaning\s+of\b", re.IGNORECASE),
]

_DEFINITIONAL_PENALTY_PATTERNS = [
    re.compile(r"\b(?:for\s+example|such\s+as|an\s+example\s+of)\b", re.IGNORECASE),
    re.compile(r"\bbecause\s+.+\s+(?:is\s+high|is\s+low|occurs|proceeds)\b", re.IGNORECASE),
    re.compile(r"\b(?:affects|influences|depends\s+on)\b", re.IGNORECASE),
]

_QUANTITATIVE_EQUATION_PATTERNS = [
    re.compile(r"\b[A-Za-z0-9_]+\s*=\s*[^,\n.]+", re.IGNORECASE),
    re.compile(r"\b(?:given|using|substituting|therefore)\s*:", re.IGNORECASE),
    re.compile(r"\b(?:mol/L|mol\s+L[-⁻]¹|J/mol|kJ/mol|K|m/s|m/s²|kg)\b"),
    re.compile(r"\b(?:values?|data|experimental\s+data)\b", re.IGNORECASE),
    re.compile(r"\b(?:solution|calculation)\s*:", re.IGNORECASE),
]

_PROCEDURAL_STEP_PATTERNS = [
    re.compile(r"\bstep\s+[1-9]\b", re.IGNORECASE),
    re.compile(r"\b(?:first|second|third|then|next|finally),?\s+", re.IGNORECASE),
    re.compile(r"\b(?:procedure|method|solution|instructions)\s*:", re.IGNORECASE),
    re.compile(r"\b(?:measure|plot|calculate|determine|substitute)\b", re.IGNORECASE),
]

_CAUSAL_MECHANISM_PATTERNS = [
    re.compile(r"\bbecause\s+.+,\s+(?:which\s+causes|leading\s+to|resulting\s+in)\b", re.IGNORECASE),
    re.compile(r"\b(?:increases|decreases)\s+.+\s+because\b", re.IGNORECASE),
    re.compile(r"\b(?:kinetic\s+energy|collision\s+frequency|fraction\s+of\s+molecules)\b", re.IGNORECASE),
    re.compile(r"\b(?:leads\s+to|results\s+in|causes)\b", re.IGNORECASE),
]

_COMPARATIVE_CONTRAST_PATTERNS = [
    re.compile(r"\b(?:in\s+contrast|whereas|while|on\s+the\s+other\s+hand)\b", re.IGNORECASE),
    re.compile(r"\b(?:difference\s+between|differences\s+are|compared\s+with)\b", re.IGNORECASE),
    re.compile(r"\b(?:unlike|distinct\s+from|distinguished\s+by)\b", re.IGNORECASE),
]

_OVERVIEW_PATTERNS = [
    re.compile(r"\b(?:in\s+this\s+chapter|this\s+section\s+covers|in\s+summary|in\s+general|overall)\b", re.IGNORECASE),
    re.compile(r"\b(?:overview|introduction)\s+to\b", re.IGNORECASE),
]


def _extract_query_target_concept(query: str) -> str:
    """Extract the primary substantive concept from query."""
    clean = re.sub(
        r"^\s*(what\s+(is|are)\s+(a|an|the)?|define|definition\s+of|meaning\s+of|explain|how\s+do\s+(i|you|we)\s+calculate|why\s+does)\s*",
        "",
        query,
        flags=re.IGNORECASE,
    ).strip().rstrip("?").lower()
    return clean


def evaluate_chunk_evidence(
    chunk_text: str,
    section: str | None,
    query_text: str,
    intent_result: QueryIntentResult | None,
) -> EvidenceQuality:
    """Evaluate a chunk's evidence quality and answer readiness for a query.

    Invariants:
    - Deterministic.
    - Zero database round trips.
    - Zero LLM calls.
    - Bounded bonus: evidence_bonus <= +0.08.
    - Preserves semantic ranking when intent is unknown or signals are neutral.
    """
    if not chunk_text or not query_text:
        return EvidenceQuality(
            directness=0.5,
            completeness=0.5,
            intent_alignment=0.5,
            concept_coverage=0.5,
            answer_marker_score=0.5,
            structural_authority=0.5,
            quality_score=0.5,
            evidence_bonus=0.0,
            reasons=(),
        )

    text_norm = unicodedata.normalize("NFKD", chunk_text)
    text_lower = text_norm.lower()
    section_lower = (section or "").lower()
    clean_query = query_text.lower().strip()

    reasons: list[str] = []
    directness = 0.50
    completeness = 0.50
    intent_alignment = 0.50
    answer_marker_score = 0.30
    structural_authority = 0.50

    # 1. Concept Coverage Assessment (via Stage 8 concept normalization)
    norm_concepts = extract_query_concepts(query_text)
    key_terms: set[str] = set()

    # Extract substantive terms from canonical concepts and normalized terms
    for c in norm_concepts.canonical_concepts:
        key_terms.add(c.lower())
    for t in norm_concepts.normalized_terms:
        if len(t) >= 4 and t not in ("what", "calculate", "explain", "describe", "why"):
            key_terms.add(t.lower())

    if not key_terms:
        # Fallback to non-trivial query words
        words = [w for w in re.findall(r"\b[a-zA-Z0-9_]+\b", clean_query) if len(w) >= 4]
        key_terms = set(words)

    if key_terms:
        matched_terms = [kt for kt in key_terms if kt in text_lower]
        concept_coverage = min(1.0, len(matched_terms) / len(key_terms))
        if concept_coverage >= 0.8:
            reasons.append(f"High concept coverage ({len(matched_terms)}/{len(key_terms)} key concepts present)")
        elif concept_coverage <= 0.3:
            reasons.append(f"Partial concept coverage ({len(matched_terms)}/{len(key_terms)})")
    else:
        concept_coverage = 0.60

    # 2. Structural Authority Evaluation
    target_concept = _extract_query_target_concept(query_text)
    if target_concept and target_concept in section_lower:
        structural_authority += 0.35
        reasons.append(f"Section heading directly contains target concept '{target_concept}'")
    elif any(h in section_lower for h in ("overview", "introduction", "fundamentals", "principles")):
        structural_authority += 0.20
        reasons.append("Structural heading indicates foundational/introductory authority")

    structural_authority = min(1.0, structural_authority)

    # 3. Intent-Specific Directness, Completeness, and Alignment
    intent = intent_result.intent if intent_result else None

    if intent == QueryIntent.DEFINITIONAL:
        intent_alignment = 0.90
        # Direct definition check
        has_direct_def = any(p.search(text_lower) for p in _DEFINITIONAL_DIRECT_PATTERNS)
        if has_direct_def:
            directness = 0.95
            completeness = 0.90
            answer_marker_score = 0.90
            reasons.append("Direct formal definition sentence identified")
            # If concept is within 50 chars of definition verb, boost further
            if target_concept and target_concept in text_lower:
                for p in _DEFINITIONAL_DIRECT_PATTERNS:
                    m = p.search(text_lower)
                    if m and abs(text_lower.find(target_concept) - m.start()) < 60:
                        directness = 1.0
                        reasons.append("Definition verb immediately proximate to target concept")
                        break
        else:
            # Check if it's merely a passing mention or consequence
            has_penalty = any(p.search(text_lower) for p in _DEFINITIONAL_PENALTY_PATTERNS)
            if has_penalty:
                directness = 0.35
                completeness = 0.40
                reasons.append("Passage discusses consequence/application rather than formal definition")
            else:
                directness = 0.50

    elif intent == QueryIntent.QUANTITATIVE:
        intent_alignment = 0.90
        has_equations = bool(re.search(r"\b[A-Za-z0-9_]+\s*=\s*", text_norm))
        has_numbers = bool(re.search(r"\b\d+(?:\.\d+)?\b", text_norm))
        has_units = bool(re.search(r"\b(?:mol/L|J/mol|kJ/mol|K|m/s|kg)\b", text_norm))
        has_solution = any(w in text_lower for w in ("given:", "using:", "therefore", "solution:", "substituting"))

        if has_equations and has_numbers and (has_units or has_solution):
            directness = 0.95
            completeness = 0.95
            answer_marker_score = 0.90
            reasons.append("Complete quantitative calculation (equation + values + solution/units)")
        elif has_equations:
            directness = 0.70
            completeness = 0.55
            reasons.append("Contains equation formula but lacks full numerical worked solution")
        else:
            directness = 0.35
            completeness = 0.30
            reasons.append("Descriptive prose without quantitative calculation steps")

    elif intent == QueryIntent.PROCEDURAL:
        intent_alignment = 0.90
        has_steps = any(p.search(text_lower) for p in _PROCEDURAL_STEP_PATTERNS)
        has_worked_ex = any(w in text_lower for w in ("worked example", "example", "solution:", "steps for"))

        if has_steps and has_worked_ex:
            directness = 0.95
            completeness = 0.95
            answer_marker_score = 0.90
            reasons.append("Complete worked procedure with ordered steps and solution")
        elif has_steps or has_worked_ex:
            directness = 0.80
            completeness = 0.75
            reasons.append("Procedural instruction markers identified")
        else:
            directness = 0.40
            completeness = 0.40
            reasons.append("Theoretical description without procedural instructions")

    elif intent == QueryIntent.COMPARATIVE:
        intent_alignment = 0.90
        has_contrast = any(p.search(text_lower) for p in _COMPARATIVE_CONTRAST_PATTERNS)
        # Check if both entities in comparative query appear in text
        comp_match = re.search(
            r"\b(?:compare|contrast|difference\s+between)\s+(.+?)\s+(?:and|with|to)\s+(.+?)(?:\?|$)",
            clean_query,
        )
        if comp_match:
            e1 = comp_match.group(1).strip()
            e2 = comp_match.group(2).strip()
            has_e1 = any(w in text_lower for w in e1.split() if len(w) > 2)
            has_e2 = any(w in text_lower for w in e2.split() if len(w) > 2)
            if has_e1 and has_e2 and has_contrast:
                directness = 0.95
                completeness = 0.95
                answer_marker_score = 0.90
                reasons.append(f"Explicitly contrasts both compared entities ('{e1}' and '{e2}')")
            elif has_e1 and has_e2:
                directness = 0.75
                completeness = 0.70
                reasons.append("Mentions both entities but lacks explicit contrastive framing")
            else:
                directness = 0.35
                completeness = 0.30
                reasons.append("Discusses only one side of the comparative query")
        elif has_contrast:
            directness = 0.75
            completeness = 0.70

    elif intent == QueryIntent.CAUSAL:
        intent_alignment = 0.90
        has_mechanism = any(p.search(text_lower) for p in _CAUSAL_MECHANISM_PATTERNS)
        has_simple_cause = any(w in text_lower for w in ("because", "causes", "results in", "therefore"))

        if has_mechanism:
            directness = 0.95
            completeness = 0.90
            answer_marker_score = 0.85
            reasons.append("Detailed mechanistic causal explanation linking factors to outcome")
        elif has_simple_cause:
            directness = 0.70
            completeness = 0.60
            reasons.append("States causal connection without full micro-mechanism")
        else:
            directness = 0.35
            completeness = 0.35
            reasons.append("Factual statement without causal mechanism")

    elif intent == QueryIntent.OVERVIEW:
        intent_alignment = 0.85
        has_overview_markers = any(p.search(text_lower) for p in _OVERVIEW_PATTERNS)
        is_intro_section = any(h in section_lower for h in ("overview", "introduction", "summary", "chapter"))

        if has_overview_markers and is_intro_section:
            directness = 0.95
            completeness = 0.90
            answer_marker_score = 0.90
            reasons.append("High-level chapter overview and introductory synthesis")
        elif has_overview_markers or is_intro_section:
            directness = 0.80
            completeness = 0.75
            reasons.append("Topical summary statement")
        else:
            directness = 0.45
            completeness = 0.45
            reasons.append("Detailed leaf subsection rather than broad overview")

    elif intent == QueryIntent.CONCEPTUAL:
        intent_alignment = 0.80
        if any(w in text_lower for w in ("process", "mechanism", "relationship", "involves", "principle")):
            directness = 0.80
            completeness = 0.75
            reasons.append("Conceptual explanation of process relationships")
        else:
            directness = 0.55
            completeness = 0.55

    else:
        # Unknown intent: neutral baseline
        intent_alignment = 0.50
        directness = 0.50
        completeness = 0.50
        answer_marker_score = 0.50

    # 4. Composite Quality Score
    quality_score = round(
        0.25 * directness
        + 0.25 * completeness
        + 0.20 * intent_alignment
        + 0.15 * concept_coverage
        + 0.15 * answer_marker_score,
        4,
    )
    quality_score = max(0.0, min(1.0, quality_score))

    # 5. Bounded Evidence Bonus (max +0.08)
    # Scaled linearly: a top-quality answer-ready chunk gets up to +0.08
    evidence_bonus = round(min(0.08, max(0.0, (quality_score - 0.40) * 0.1333)), 6)

    return EvidenceQuality(
        directness=directness,
        completeness=completeness,
        intent_alignment=intent_alignment,
        concept_coverage=concept_coverage,
        answer_marker_score=answer_marker_score,
        structural_authority=structural_authority,
        quality_score=quality_score,
        evidence_bonus=evidence_bonus,
        reasons=tuple(reasons),
    )


def evaluate_cluster_evidence(
    cluster_items: Sequence[SearchResultItemDTO],
    query_text: str,
    intent_result: QueryIntentResult | None,
) -> ClusterEvidenceQuality:
    """Evaluate whether an expanded sequence cluster forms an answer-ready evidence unit."""
    if not cluster_items:
        return ClusterEvidenceQuality(
            core_chunk_id=uuid.uuid4(),
            cluster_size=0,
            is_answer_ready=False,
            cluster_score=0.0,
            combined_concept_coverage=0.0,
            reasons=(),
        )

    core_item = cluster_items[0]
    combined_text = " ".join(item.text for item in cluster_items)
    cluster_size = len(cluster_items)

    reasons: list[str] = []

    # Check combined concept coverage
    norm_concepts = extract_query_concepts(query_text)
    key_terms: set[str] = set()
    for c in norm_concepts.canonical_concepts:
        key_terms.add(c.lower())
    for t in norm_concepts.normalized_terms:
        if len(t) >= 4 and t not in ("what", "calculate", "explain", "describe", "why"):
            key_terms.add(t.lower())

    text_lower = combined_text.lower()
    if key_terms:
        matched = [kt for kt in key_terms if kt in text_lower]
        combined_coverage = min(1.0, len(matched) / len(key_terms))
    else:
        combined_coverage = 0.70

    # Check for multi-chunk procedural continuity (Step 1 -> Step 2 -> Calculation -> Result)
    intent = intent_result.intent if intent_result else None
    has_step1 = bool(re.search(r"\bstep\s*1\b", text_lower))
    has_step2 = bool(re.search(r"\bstep\s*2\b", text_lower))
    has_formula = bool(re.search(r"\b[A-Za-z0-9_]+\s*=\s*", combined_text))
    has_solution = bool(re.search(r"\b(?:solution|therefore|result|answer)\b", text_lower))

    is_answer_ready = False
    if intent in (QueryIntent.PROCEDURAL, QueryIntent.QUANTITATIVE):
        if (has_step1 and has_step2) or (has_formula and has_solution):
            is_answer_ready = True
            reasons.append("Cluster provides complete step-by-step procedural derivation and solution")
    elif combined_coverage >= 0.8 and cluster_size >= 2:
        is_answer_ready = True
        reasons.append("Cluster provides comprehensive coverage across all query concepts")

    cluster_score = round(min(1.0, 0.5 * core_item.score + 0.3 * combined_coverage + (0.2 if is_answer_ready else 0.0)), 4)

    return ClusterEvidenceQuality(
        core_chunk_id=core_item.chunk_id,
        cluster_size=cluster_size,
        is_answer_ready=is_answer_ready,
        cluster_score=cluster_score,
        combined_concept_coverage=combined_coverage,
        reasons=tuple(reasons),
    )
