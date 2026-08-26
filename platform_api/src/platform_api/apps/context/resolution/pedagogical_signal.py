from __future__ import annotations

import re
from collections.abc import Sequence

from platform_api.apps.context.resolution.dto import (
    ContextSignal,
    ExplicitGeographicIntent,
)

# Deterministic phrases indicating explicit local/geographical context intent
LOCALITY_PHRASES: tuple[str, ...] = (
    "in my area",
    "in our area",
    "from my area",
    "from our area",
    "locally",
    "where i live",
    "where we live",
    "in my region",
    "in our region",
    "from my region",
    "from our region",
    "in my district",
    "in our district",
    "from my district",
    "from our district",
    "in my county",
    "in my subcounty",
    "in my parish",
    "in my village",
    "in our village",
    "in my town",
    "in our town",
    "in my country",
    "in our country",
    "local example",
    "local context",
    "local farming",
    "local community",
    "local school",
    "local environment",
    "local economy",
    "local practices",
    "around here",
    "near me",
    "in uganda",
    "in kenya",
    "in tanzania",
    "in rwanda",
    "in east africa",
)

# Domain vocabulary that strongly benefits from localized pedagogical examples
CONTEXT_TERMS: tuple[str, ...] = (
    "agriculture",
    "farming",
    "crops",
    "crop production",
    "cash crop",
    "food crop",
    "tea estate",
    "coffee farming",
    "matooke",
    "cassava",
    "maize",
    "soil erosion",
    "soil fertility",
    "rainfall",
    "rainy season",
    "dry season",
    "bimodal rainfall",
    "climate",
    "weather pattern",
    "topography",
    "vegetation",
    "wetland",
    "swamp",
    "pastoralism",
    "cattle keeping",
    "livestock",
    "local market",
    "local government",
    "district administration",
    "cultural tradition",
    "indigenous knowledge",
    "traditional practice",
    "afforestation",
    "deforestation",
    "water catchment",
)

CONTEXT_RELEVANT_SUBJECTS: frozenset[str] = frozenset(
    {
        "agriculture",
        "geography",
        "social studies",
        "environmental science",
        "biology",
        "economics",
    }
)


def detect_pedagogical_signal(
    prompt: str,
    explicit_intent: ExplicitGeographicIntent | None = None,
    subjects: Sequence[str] | None = None,
    topics: Sequence[str] | None = None,
    purposes: Sequence[str] | None = None,
) -> ContextSignal:
    """Deterministically determine whether geographical context should be considered.

    Signals evaluated:
    1. Explicit geographic intent detected.
    2. Explicit locality/regional phrases in prompt.
    3. Context-relevant domain vocabulary in prompt.
    4. Relevant subject/topic/purpose metadata.
    """
    if not prompt or not prompt.strip():
        return ContextSignal(
            context_relevant=False,
            explicit_geography_detected=False,
            detected_terms=[],
            reason="Empty prompt.",
        )

    # 1. Explicit geographic location takes immediate priority
    if explicit_intent is not None:
        return ContextSignal(
            context_relevant=True,
            explicit_geography_detected=True,
            detected_terms=[explicit_intent.matched_text],
            reason=(
                f"Explicit geographic entity '{explicit_intent.unit_name}' referenced."
            ),
        )

    lower_prompt = prompt.lower()
    detected_terms: list[str] = []

    # 2. Check locality phrases
    for phrase in LOCALITY_PHRASES:
        if phrase in lower_prompt:
            detected_terms.append(phrase)

    # 3. Check domain vocabulary (with word boundaries)
    for term in CONTEXT_TERMS:
        pattern = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
        if pattern.search(prompt):
            detected_terms.append(term)

    # 4. Check subject/topic metadata
    normalized_subjects = [s.strip().lower() for s in (subjects or [])]
    subject_match = any(s in CONTEXT_RELEVANT_SUBJECTS for s in normalized_subjects)
    if subject_match:
        detected_terms.extend(
            [s for s in normalized_subjects if s in CONTEXT_RELEVANT_SUBJECTS]
        )

    if detected_terms:
        unique_terms = list(dict.fromkeys(detected_terms))
        return ContextSignal(
            context_relevant=True,
            explicit_geography_detected=False,
            detected_terms=unique_terms,
            reason=(
                f"Pedagogical contextual relevance detected via terms: "
                f"{', '.join(unique_terms[:3])}."
            ),
        )

    # If no contextual signals were found, context is deemed not relevant
    return ContextSignal(
        context_relevant=False,
        explicit_geography_detected=False,
        detected_terms=[],
        reason="No geographic or localized pedagogical signals detected in request.",
    )
