"""Deterministic query intent recognition and intent-guided ranking priors."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum


class QueryIntent(str, Enum):
    """Recognized conceptual intent of a learner's query."""

    DEFINITIONAL = "definitional"
    PROCEDURAL = "procedural"
    OVERVIEW = "overview"
    CONCEPTUAL = "conceptual"
    COMPARATIVE = "comparative"
    CAUSAL = "causal"
    QUANTITATIVE = "quantitative"


@dataclass(frozen=True)
class QueryIntentResult:
    """Result of deterministic query intent recognition."""

    intent: QueryIntent | None
    confidence: float  # 0.0 to 1.0
    matched_cue: str | None
    intents: frozenset[QueryIntent] = frozenset()


# Deterministic precedence: QUANTITATIVE > PROCEDURAL > COMPARATIVE > DEFINITIONAL > CAUSAL > CONCEPTUAL > OVERVIEW
INTENT_PRECEDENCE = [
    QueryIntent.QUANTITATIVE,
    QueryIntent.PROCEDURAL,
    QueryIntent.COMPARATIVE,
    QueryIntent.DEFINITIONAL,
    QueryIntent.CAUSAL,
    QueryIntent.CONCEPTUAL,
    QueryIntent.OVERVIEW,
]

_QUANTITATIVE_PATTERNS = [
    (re.compile(r"^\s*(calculate|compute)\b", re.IGNORECASE), 0.95),
    (re.compile(r"\bfind\s+the\s+value(\s+of)?\b", re.IGNORECASE), 0.95),
    (re.compile(r"\bvalue\s+of\s+[A-Za-z0-9_]+\b", re.IGNORECASE), 0.90),
    (re.compile(r"\bwhat\s+is\s+the\s+(acceleration|velocity|concentration|rate\s+constant|equilibrium\s+constant)\s+if\b", re.IGNORECASE), 0.90),
    (re.compile(r"\bnumerical\s+(value|problem)\b", re.IGNORECASE), 0.90),
    (re.compile(r"\bnumerical\b", re.IGNORECASE), 0.85),
]

_PROCEDURAL_PATTERNS = [
    (re.compile(r"^\s*how\s+(do\s+(i|you|we)|to|can\s+we)\s+(calculate|find|solve|determine|compute)\b", re.IGNORECASE), 0.95),
    (re.compile(r"^\s*(how\s+to|how\s+do\s+(i|you|we))\b", re.IGNORECASE), 0.90),
    (re.compile(r"^\s*(solve|procedure\s+for|steps?\s+(for|to))\b", re.IGNORECASE), 0.90),
    (re.compile(r"\bhow\s+is\s+.+\s+calculated\b", re.IGNORECASE), 0.85),
]

_COMPARATIVE_PATTERNS = [
    (re.compile(r"^\s*(compare|contrast)\b", re.IGNORECASE), 0.95),
    (re.compile(r"\b(what\s+is\s+the\s+)?difference\s+between\b", re.IGNORECASE), 0.95),
    (re.compile(r"\bhow\s+(are|do)\s+.+\s+different\b", re.IGNORECASE), 0.90),
    (re.compile(r"\bdistinguish\s+between\b", re.IGNORECASE), 0.90),
]

_DEFINITIONAL_PATTERNS = [
    (re.compile(r"^\s*what\s+(is|are)\s+(a|an|the)?\s*", re.IGNORECASE), 0.95),
    (re.compile(r"^\s*(define|definition\s+of|meaning\s+of|what\s+is\s+meant\s+by)\b", re.IGNORECASE), 0.95),
    (re.compile(r"\bwhat\s+does\s+.+\s+mean\b", re.IGNORECASE), 0.90),
    (re.compile(r"\bis\s+defined\s+as\b", re.IGNORECASE), 0.85),
]

_CAUSAL_PATTERNS = [
    (re.compile(r"^\s*why\s+(does|do|is|are|would|will|did)?\b", re.IGNORECASE), 0.95),
    (re.compile(r"^\s*why\b", re.IGNORECASE), 0.90),
    (re.compile(r"^\s*how\s+does\s+.+\s+(affect|influence|work|change|impact|make)\b", re.IGNORECASE), 0.90),
    (re.compile(r"^\s*how\s+do\b", re.IGNORECASE), 0.85),
    (re.compile(r"\bwhat\s+causes\b", re.IGNORECASE), 0.90),
    (re.compile(r"\bwhy\s+does\b", re.IGNORECASE), 0.90),
    (re.compile(r"^\s*what\s+is\s+the\s+role\s+of\b", re.IGNORECASE), 0.85),
]

_CONCEPTUAL_PATTERNS = [
    (re.compile(r"^\s*describe\s+the\s+process\s+of\b", re.IGNORECASE), 0.90),
    (re.compile(r"\brelationship\s+between\b", re.IGNORECASE), 0.90),
    (re.compile(r"^\s*how\s+are\s+.+\s+involved\b", re.IGNORECASE), 0.85),
    (re.compile(r"\bmechanism\s+of\b", re.IGNORECASE), 0.85),
]

_OVERVIEW_PATTERNS = [
    (re.compile(r"^\s*give\s+an\s+overview\s+of\b", re.IGNORECASE), 0.90),
    (re.compile(r"^\s*overview\s+of\b", re.IGNORECASE), 0.90),
    (re.compile(r"^\s*(summarize|summary\s+of)\b", re.IGNORECASE), 0.90),
    (re.compile(r"^\s*explain\s+(the\s+topic\s+of|in\s+general|broadly)?\s*", re.IGNORECASE), 0.80),
    (re.compile(r"^\s*describe\b", re.IGNORECASE), 0.75),
    (re.compile(r"^\s*introduction\s+to\b", re.IGNORECASE), 0.80),
    (re.compile(r"\boverview\b", re.IGNORECASE), 0.75),
]


def detect_query_intent(query: str) -> QueryIntentResult:
    """Classify the conceptual intent of a learner's query using deterministic signals.

    Invariants:
    - Zero LLM calls.
    - Zero external service or database dependencies.
    - Deterministic precedence: QUANTITATIVE > PROCEDURAL > COMPARATIVE > DEFINITIONAL > CAUSAL > CONCEPTUAL > OVERVIEW.
    - Preserves all matched intents in the `intents` set.
    """
    if not query or not query.strip():
        return QueryIntentResult(intent=None, confidence=0.0, matched_cue=None)

    clean_query = unicodedata.normalize("NFC", query).strip()

    matched: dict[QueryIntent, tuple[float, str]] = {}

    for pattern, conf in _QUANTITATIVE_PATTERNS:
        m = pattern.search(clean_query)
        if m:
            matched[QueryIntent.QUANTITATIVE] = (conf, m.group(0).strip())
            break

    for pattern, conf in _PROCEDURAL_PATTERNS:
        m = pattern.search(clean_query)
        if m:
            matched[QueryIntent.PROCEDURAL] = (conf, m.group(0).strip())
            break

    for pattern, conf in _COMPARATIVE_PATTERNS:
        m = pattern.search(clean_query)
        if m:
            matched[QueryIntent.COMPARATIVE] = (conf, m.group(0).strip())
            break

    for pattern, conf in _DEFINITIONAL_PATTERNS:
        m = pattern.search(clean_query)
        if m:
            matched[QueryIntent.DEFINITIONAL] = (conf, m.group(0).strip())
            break

    for pattern, conf in _CAUSAL_PATTERNS:
        m = pattern.search(clean_query)
        if m:
            matched[QueryIntent.CAUSAL] = (conf, m.group(0).strip())
            break

    for pattern, conf in _CONCEPTUAL_PATTERNS:
        m = pattern.search(clean_query)
        if m:
            matched[QueryIntent.CONCEPTUAL] = (conf, m.group(0).strip())
            break

    for pattern, conf in _OVERVIEW_PATTERNS:
        m = pattern.search(clean_query)
        if m:
            matched[QueryIntent.OVERVIEW] = (conf, m.group(0).strip())
            break

    if not matched:
        return QueryIntentResult(intent=None, confidence=0.0, matched_cue=None)

    # Pick primary intent according to precedence order
    for intent_candidate in INTENT_PRECEDENCE:
        if intent_candidate in matched:
            conf, cue = matched[intent_candidate]
            return QueryIntentResult(
                intent=intent_candidate,
                confidence=conf,
                matched_cue=cue,
                intents=frozenset(matched.keys()),
            )

    primary = next(iter(matched))
    conf, cue = matched[primary]
    return QueryIntentResult(
        intent=primary,
        confidence=conf,
        matched_cue=cue,
        intents=frozenset(matched.keys()),
    )


def classify_query_intent(query: str) -> QueryIntent:
    """Convenience helper returning the primary QueryIntent enum, defaulting to CONCEPTUAL."""
    res = detect_query_intent(query)
    return res.intent or QueryIntent.CONCEPTUAL


# Definitional phrasing indicators inside chunk text
_DEFINITIONAL_TEXT_CUES = [
    "is defined as",
    "are defined as",
    "can be defined as",
    "refers to",
    "meaning of",
    "is known as",
    "denotes",
    "is the",
    "are the",
    "minimum energy",
]

_PROCEDURAL_TEXT_CUES = [
    "worked example",
    "example",
    "solution:",
    "step 1",
    "step 2",
    "formula",
    "equation",
    "substitute",
    "substituting",
    "calculate",
    "units",
]

_OVERVIEW_TEXT_CUES = [
    "in this chapter",
    "in summary",
    "in general",
    "overall",
    "overview",
    "introduction",
    "first",
]

_CAUSAL_TEXT_CUES = [
    "because",
    "therefore",
    "leads to",
    "results in",
    "causes",
    "increases",
    "decreases",
    "due to",
    "proportional to",
    "activation energy",
    "collision",
    "kinetic energy",
]

_COMPARATIVE_TEXT_CUES = [
    "whereas",
    "while",
    "compared with",
    "difference",
    "similar",
    "different",
    "in contrast",
    "both",
    "on the other hand",
]


def _extract_comparative_entities(query: str) -> tuple[str, str] | None:
    """Extract entity pair from comparative query (e.g. 'compare X and Y')."""
    m = re.search(r"\b(?:compare|contrast|difference\s+between)\s+(.+?)\s+(?:and|with|to)\s+(.+?)(?:\?|$)", query, re.IGNORECASE)
    if m:
        return m.group(1).strip().lower(), m.group(2).strip().lower()
    return None


def compute_intent_bonus(
    chunk_text: str,
    section: str | None,
    query_text: str,
    intent_result: QueryIntentResult | None,
) -> float:
    """Compute a bounded intent score bonus (max +0.06) based on query intent.

    Invariants:
    - Deterministic.
    - Strictly bounded in [0.0, 0.06].
    - Zero bonus when intent is None.
    - Cannot override strong semantic differences.
    """
    if not intent_result or not intent_result.intent or intent_result.confidence <= 0:
        return 0.0

    intent = intent_result.intent
    text_lower = chunk_text.lower()
    section_lower = (section or "").lower()

    bonus = 0.0

    if intent == QueryIntent.DEFINITIONAL:
        has_cue = any(cue in text_lower for cue in _DEFINITIONAL_TEXT_CUES)
        if has_cue:
            bonus += 0.04

        target_concept = re.sub(
            r"^\s*(what\s+(is|are)\s+(a|an|the)?|define|definition\s+of|meaning\s+of)\s*",
            "",
            query_text,
            flags=re.IGNORECASE,
        ).strip().rstrip("?").lower()

        if target_concept and len(target_concept) >= 3:
            for cue in _DEFINITIONAL_TEXT_CUES:
                if cue in text_lower and target_concept in text_lower:
                    pos_cue = text_lower.find(cue)
                    pos_concept = text_lower.find(target_concept)
                    if abs(pos_cue - pos_concept) < 80:
                        bonus += 0.02
                        break

            if target_concept in section_lower:
                bonus += 0.01

    elif intent in (QueryIntent.PROCEDURAL, QueryIntent.QUANTITATIVE):
        has_cue = any(cue in text_lower for cue in _PROCEDURAL_TEXT_CUES)
        if has_cue:
            bonus += 0.04

        if any(sym in chunk_text for sym in ["=", "×", "÷", "^2", "[", "]", "mol/L"]):
            bonus += 0.02

    elif intent == QueryIntent.OVERVIEW:
        if any(h in section_lower for h in ["overview", "introduction", "summary"]):
            bonus += 0.04

        if any(cue in text_lower for cue in _OVERVIEW_TEXT_CUES):
            bonus += 0.02

    elif intent == QueryIntent.CAUSAL:
        has_cue = any(cue in text_lower for cue in _CAUSAL_TEXT_CUES)
        if has_cue:
            bonus += 0.04

        if any(w in section_lower for w in ["kinetics", "mechanism", "principles", "theory"]):
            bonus += 0.02

    elif intent == QueryIntent.COMPARATIVE:
        has_cue = any(cue in text_lower for cue in _COMPARATIVE_TEXT_CUES)
        if has_cue:
            bonus += 0.02

        entities = _extract_comparative_entities(query_text)
        if entities:
            e1, e2 = entities
            w1 = [w for w in e1.split() if len(w) > 2]
            w2 = [w for w in e2.split() if len(w) > 2]
            has_e1 = any(w in text_lower for w in w1) if w1 else e1 in text_lower
            has_e2 = any(w in text_lower for w in w2) if w2 else e2 in text_lower
            if has_e1 and has_e2:
                bonus += 0.04

    elif intent == QueryIntent.CONCEPTUAL:
        if any(w in section_lower for w in ["concept", "process", "principles", "relationship"]):
            bonus += 0.02
        if any(w in text_lower for w in ["relationship", "process", "mechanism", "involves"]):
            bonus += 0.02

    return round(min(0.06, bonus), 6)
