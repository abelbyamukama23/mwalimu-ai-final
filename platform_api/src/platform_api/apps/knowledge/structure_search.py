"""Structure search service for navigating document hierarchy before vector retrieval."""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Sequence

from platform_api.apps.processing.models import DocumentStructureNode

from .concept_normalization import extract_query_concepts
from .policies import EffectiveRetrievalScope


# Standard English stop words to filter out incidental generic tokens
STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other",
    "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't",
    "she", "should", "shouldn't", "so", "some", "such", "than", "that", "the",
    "their", "theirs", "them", "themselves", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "under", "until", "up", "very", "was",
    "wasn't", "we", "were", "weren't", "what", "when", "where", "which", "while",
    "who", "whom", "why", "with", "won't", "would", "wouldn't", "you", "your",
    "yours", "yourself", "yourselves",
    # Question & generic verbs
    "explain", "describe", "discuss", "affect", "affects", "affecting", "cause",
    "causes", "causing", "mean", "means", "meaning", "define", "definition",
}


def _tokenize(text: str) -> list[str]:
    """Tokenize and normalize text into meaningful content words."""
    cleaned = unicodedata.normalize("NFC", text).lower()
    words = re.findall(r"\b[a-z0-9]+(?:'[a-z]+)?\b", cleaned)
    return [w for w in words if w not in STOP_WORDS and len(w) > 1]


def _extract_ngrams(tokens: list[str]) -> list[str]:
    """Extract bigrams and trigrams from tokens."""
    ngrams: list[str] = []
    if len(tokens) >= 2:
        for i in range(len(tokens) - 1):
            ngrams.append(f"{tokens[i]} {tokens[i+1]}")
    if len(tokens) >= 3:
        for i in range(len(tokens) - 2):
            ngrams.append(f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}")
    return ngrams


def _get_all_descendant_ids(
    parent_ids: set[uuid.UUID],
    all_nodes: Sequence[DocumentStructureNode],
) -> set[uuid.UUID]:
    """Recursively collect all child and descendant structure node IDs."""
    descendants = set(parent_ids)
    current_parents = set(parent_ids)

    while current_parents:
        children = [
            n.id
            for n in all_nodes
            if n.parent_id in current_parents and n.id not in descendants
        ]
        if not children:
            break
        descendants.update(children)
        current_parents = set(children)

    return descendants


def find_candidate_structure_nodes(
    query: str,
    scope: EffectiveRetrievalScope,
    min_score_threshold: float = 2.0,
) -> list[uuid.UUID]:
    """Identify candidate DocumentStructureNode IDs matching the query concept.

    Args:
        query: Raw search query.
        scope: Effective authorized retrieval scope.
        min_score_threshold: Minimum structural relevance score required.

    Returns:
        List of candidate DocumentStructureNode UUIDs (including descendants).
    """
    if scope.is_empty:
        return []

    # 1. Extract query content tokens, n-grams, and normalized concepts
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    query_ngrams = set(_extract_ngrams(query_tokens))
    query_token_set = set(query_tokens)
    norm_concepts = extract_query_concepts(query)

    # 2. Query active DocumentStructureNodes within authorized scope
    try:
        qs = DocumentStructureNode.objects.filter(
            library_id__in=scope.authorized_library_ids,
            processing_run__is_active=True,
            processing_run__status="ready",
        )
        if scope.authorized_resource_ids is not None:
            qs = qs.filter(resource_id__in=scope.authorized_resource_ids)

        nodes = list(qs.select_related("parent"))
    except Exception:
        return []

    if not nodes:
        return []

    # 3. Score each node based on structural title relevance
    node_scores: list[tuple[float, DocumentStructureNode]] = []

    for node in nodes:
        title_norm = unicodedata.normalize("NFC", node.title).lower()
        title_tokens = _tokenize(node.title)
        title_token_set = set(title_tokens)
        title_ngrams = set(_extract_ngrams(title_tokens))

        score = 0.0

        # Exact phrase containment (highest weight)
        for ngram in query_ngrams:
            if ngram in title_norm:
                score += 5.0

        # Canonical concept containment (from technical aliases)
        for concept in norm_concepts.canonical_concepts:
            if concept in title_norm:
                score += 5.0

        # Bigram overlap
        common_ngrams = query_ngrams.intersection(title_ngrams)
        score += len(common_ngrams) * 4.0

        # Individual token overlap
        common_tokens = query_token_set.intersection(title_token_set)
        if len(common_tokens) >= 2:
            score += len(common_tokens) * 2.5
        elif len(common_tokens) == 1:
            single_tok = next(iter(common_tokens))
            if len(single_tok) >= 5:
                score += 2.5
            elif len(single_tok) >= 3:
                score += 1.5

        # Morphological and alias matches (e.g. catalyst in query matching catalysis in title)
        for term in norm_concepts.normalized_terms:
            if term not in query_token_set and len(term) >= 4:
                if term in title_norm or term in title_token_set:
                    score += 3.0

        if score >= min_score_threshold:
            node_scores.append((score, node))


    if not node_scores:
        return []


    # Sort descending by score
    node_scores.sort(key=lambda x: x[0], reverse=True)

    # Take top scoring nodes (within 50% of the top score)
    top_score = node_scores[0][0]
    best_nodes = [node for s, node in node_scores if s >= top_score * 0.5]

    # Collect all candidate node IDs plus their descendants
    best_node_ids = {n.id for n in best_nodes}
    all_candidate_ids = _get_all_descendant_ids(best_node_ids, nodes)

    return list(all_candidate_ids)
