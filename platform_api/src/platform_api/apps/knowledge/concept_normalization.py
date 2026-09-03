"""Deterministic concept normalization and technical alias registry.

This module provides controlled, conservative vocabulary normalization for textbook concepts
without aggressive stemming that would distort technical terminology.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class ConceptNormalizationResult:
    """Result of concept normalization and alias expansion for a query or term."""

    original_term: str
    normalized_terms: tuple[str, ...]
    canonical_concepts: tuple[str, ...]
    aliases_applied: tuple[tuple[str, str], ...]  # (alias, canonical_concept)


# Controlled technical alias registry:
# maps normalized alias strings to canonical concept forms.
# Invariants:
# - Deterministic, inspectable, and versionable.
# - Explicitly separates distinct scientific entities (e.g. Ea vs Kc vs Ka vs Ksp).
TECHNICAL_ALIAS_REGISTRY: dict[str, str] = {
    # Activation energy aliases
    "ea": "activation energy",
    "e_a": "activation energy",
    "e a": "activation energy",
    "eₐ": "activation energy",
    "activation energy": "activation energy",
    # Equilibrium constant aliases
    "kc": "equilibrium constant",
    "k_c": "equilibrium constant",
    "k c": "equilibrium constant",
    "kc equilibrium constant": "equilibrium constant",
    "equilibrium constant": "equilibrium constant",
    # Enthalpy change aliases
    "δh": "enthalpy change",
    "delta h": "enthalpy change",
    "delta_h": "enthalpy change",
    "enthalpy change": "enthalpy change",
    # Reaction rate
    "reaction rate": "reaction rate",
    "reaction rates": "reaction rate",
    "rate of reaction": "reaction rate",
    # Arrhenius
    "arrhenius": "arrhenius equation",
    "arrhenius equation": "arrhenius equation",
}

# Conservative morphological suffix mappings:
# Only safe, regular plural-to-singular transformations.
_CONSERVATIVE_SUFFIX_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ies$"), "y"),       # properties -> property
    (re.compile(r"(s|x|z|ch|sh)es$"), r"\1"),  # processes -> process, gases -> gas
    (re.compile(r"([a-z0-9]{3,})s$"), r"\1"),  # catalysts -> catalyst, reactions -> reaction, molecules -> molecule
]

# Explicit semantic-morphological equivalents in textbook science:
# Bidirectional bridges between noun forms, plurals, and adjectival/process forms
_ACADEMIC_EQUIVALENCES: dict[str, tuple[str, ...]] = {
    "catalyst": ("catalysis", "catalysts", "catalytic"),
    "catalysis": ("catalyst", "catalysts", "catalytic"),
    "catalysts": ("catalyst", "catalysis", "catalytic"),
    "catalytic": ("catalyst", "catalysis", "catalysts"),
    "reaction": ("reactions", "reacting", "reactants"),
    "reactions": ("reaction", "reacting", "reactants"),
    "molecule": ("molecules", "molecular"),
    "molecules": ("molecule", "molecular"),
    "molecular": ("molecule", "molecules"),
    "equation": ("equations",),
    "equations": ("equation",),
    "temperature": ("temperatures",),
    "temperatures": ("temperature",),
    "equilibrium": ("equilibria",),
    "equilibria": ("equilibrium",),
    "ferment": ("fermentation", "fermenting"),
    "fermentation": ("ferment", "fermenting"),
    "photosynthetic": ("photosynthesis",),
    "photosynthesis": ("photosynthetic",),
}

# Negative list: Terms that must NEVER be collapsed or stripped
_PROTECTED_TERMS = {
    "ka", "ksp", "kw", "kp", "ph", "poh", "dna", "rna", "atp", "adp",
    "organ", "organic", "relative", "relativity", "general", "generic",
    "mass", "gas", "basis", "axis", "species", "series", "corpus",
}


def normalize_token_morphology(token: str) -> list[str]:
    """Conservatively normalize a single word token to its base/equivalent forms.

    Invariants:
    - Never destroys protected short technical terms (e.g. ka, ksp, ph, gas, mass).
    - Preserves original token as the first element.
    - Deterministic.
    """
    clean = unicodedata.normalize("NFKD", token).lower().strip()
    if not clean or len(clean) < 2:
        return [clean] if clean else []

    if clean in _PROTECTED_TERMS:
        return [clean]

    variants: list[str] = [clean]

    # 1. Academic explicit equivalence lookup
    if clean in _ACADEMIC_EQUIVALENCES:
        for equiv in _ACADEMIC_EQUIVALENCES[clean]:
            if equiv not in variants:
                variants.append(equiv)

    # 2. Conservative plural stripping
    for pattern, repl in _CONSERVATIVE_SUFFIX_RULES:
        if pattern.search(clean):
            base = pattern.sub(repl, clean)
            if base and base not in variants and base not in _PROTECTED_TERMS:
                variants.append(base)
                # If base has academic equivalences, add them too
                if base in _ACADEMIC_EQUIVALENCES:
                    for equiv in _ACADEMIC_EQUIVALENCES[base]:
                        if equiv not in variants:
                            variants.append(equiv)
            break

    return variants


def extract_query_concepts(query: str) -> ConceptNormalizationResult:
    """Extract, normalize, and resolve concepts from a search query.

    Invariants:
    - Zero LLM calls.
    - Pure in-memory deterministic lookup.
    - Does NOT fabricate unmentioned concepts (e.g. will not add 'activation energy'
      unless an explicit alias like 'Ea' or the phrase itself is present).
    """
    if not query or not query.strip():
        return ConceptNormalizationResult(
            original_term="",
            normalized_terms=(),
            canonical_concepts=(),
            aliases_applied=(),
        )

    clean_raw = unicodedata.normalize("NFKD", query).strip()
    clean_lower = clean_raw.lower()

    normalized_terms_set: set[str] = set()
    canonical_concepts_set: set[str] = set()
    aliases_applied: list[tuple[str, str]] = []

    # 1. Check for exact multi-word aliases first in query text
    for alias, canonical in TECHNICAL_ALIAS_REGISTRY.items():
        # Match as whole word/symbol boundary
        escaped_alias = re.escape(alias)
        pattern = rf"(?<![a-zA-Z0-9_]){escaped_alias}(?![a-zA-Z0-9_])"
        if re.search(pattern, clean_lower):
            canonical_concepts_set.add(canonical)
            normalized_terms_set.add(canonical)
            normalized_terms_set.add(alias)
            if alias != canonical:
                aliases_applied.append((alias, canonical))

    # 2. Tokenize words and sub-phrases
    tokens = re.findall(r"\b[a-zA-Z0-9_]+(?:'[a-zA-Z]+)?\b", clean_lower)

    # Check individual tokens against aliases
    for t in tokens:
        if t in TECHNICAL_ALIAS_REGISTRY:
            canonical = TECHNICAL_ALIAS_REGISTRY[t]
            canonical_concepts_set.add(canonical)
            normalized_terms_set.add(canonical)
            normalized_terms_set.add(t)
            if t != canonical:
                aliases_applied.append((t, canonical))

        # Apply conservative morphological normalization
        for norm in normalize_token_morphology(t):
            normalized_terms_set.add(norm)

    # 3. Generate bigrams from tokens to check against aliases
    if len(tokens) >= 2:
        for i in range(len(tokens) - 1):
            bigram = f"{tokens[i]} {tokens[i+1]}"
            if bigram in TECHNICAL_ALIAS_REGISTRY:
                canonical = TECHNICAL_ALIAS_REGISTRY[bigram]
                canonical_concepts_set.add(canonical)
                normalized_terms_set.add(canonical)
                normalized_terms_set.add(bigram)
                if bigram != canonical:
                    aliases_applied.append((bigram, canonical))

    return ConceptNormalizationResult(
        original_term=query,
        normalized_terms=tuple(sorted(normalized_terms_set)),
        canonical_concepts=tuple(sorted(canonical_concepts_set)),
        aliases_applied=tuple(aliases_applied),
    )
