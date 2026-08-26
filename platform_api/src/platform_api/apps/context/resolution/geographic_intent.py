from __future__ import annotations

import re
from collections.abc import Sequence

from platform_api.apps.context.models import GeographicUnit, GeographicUnitStatus
from platform_api.apps.context.resolution.dto import ExplicitGeographicIntent


def detect_geographic_intent(
    prompt: str,
    geographic_units: Sequence[GeographicUnit] | None = None,
) -> ExplicitGeographicIntent | None:
    """Detect if the prompt explicitly references a registered active geographic unit.

    Uses whole-word boundary regex matching on name, slug, and metadata aliases.
    Prioritizes longer/more specific matches to avoid partial ambiguities.
    """
    if not prompt or not prompt.strip():
        return None

    if geographic_units is None:
        geographic_units = list(
            GeographicUnit.objects.filter(status=GeographicUnitStatus.ACTIVE)
        )

    # Sort units by name length descending so multi-word units match first
    sorted_units = sorted(geographic_units, key=lambda u: len(u.name), reverse=True)

    for unit in sorted_units:
        # Build list of search terms for this unit
        terms: list[str] = [unit.name]
        slug_clean = unit.slug.replace("-", " ")
        if slug_clean.lower() != unit.name.lower():
            terms.append(slug_clean)

        if isinstance(unit.metadata, dict):
            aliases = unit.metadata.get("aliases")
            if isinstance(aliases, list):
                for alias in aliases:
                    if isinstance(alias, str) and alias.strip():
                        terms.append(alias.strip())

        for term in terms:
            clean_term = term.strip()
            if len(clean_term) < 2:
                continue

            # Word-boundary case-insensitive regex
            pattern = re.compile(
                r"\b" + re.escape(clean_term) + r"\b",
                re.IGNORECASE,
            )
            match = pattern.search(prompt)
            if match:
                matched_text = match.group(0)
                return ExplicitGeographicIntent(
                    geographic_unit_id=unit.id,
                    unit_name=unit.name,
                    unit_type=unit.unit_type,
                    matched_text=matched_text,
                    reason=(
                        f"Explicit prompt mention of '{matched_text}' "
                        f"matching {unit.name}."
                    ),
                )

    return None
