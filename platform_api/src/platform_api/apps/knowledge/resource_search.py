"""Deterministic resource/book disambiguation and prioritization."""

from __future__ import annotations

import unicodedata
import uuid
from dataclasses import dataclass

from platform_api.apps.processing.models import DocumentStructureNode, ProcessingStatus
from platform_api.apps.resources.models import Resource, ResourceStatus

from .policies import EffectiveRetrievalScope
from .structure_search import _extract_ngrams, _tokenize


@dataclass(frozen=True)
class ResourceCandidate:
    """Relevance score and matched evidence signals for an authorized resource."""

    resource_id: uuid.UUID
    resource_name: str
    score: float
    matched_signals: tuple[str, ...]


@dataclass(frozen=True)
class ResourcePriorResult:
    """Result of deterministic resource prior scoring and selection."""

    prioritized_resource_ids: tuple[uuid.UUID, ...]
    all_scored_resources: tuple[ResourceCandidate, ...]
    confidence: float  # 0.0 to 1.0
    is_scope_restricted: bool


def rank_candidate_resources(
    query: str,
    scope: EffectiveRetrievalScope,
) -> list[ResourceCandidate]:
    """Score and rank all authorized resources in scope based on title and structural headings.

    Evidence Priority:
    1. Exact phrase match in resource title (Highest weight: +10.0)
    2. N-gram / token overlap with resource title (+6.0 / +4.0)
    3. Top-level chapter heading matches (level=1: +6.0 / +3.0)
    4. Section heading matches (level=2: +4.0 / +2.0)

    Invariants:
    - Strictly scoped to scope.authorized_library_ids and scope.authorized_resource_ids.
    - Strictly scoped to active, ready processing runs and ready resources.
    - Deterministic and explainable.
    - Zero N+1 queries: single query for resources, single query for headings.
    """
    if not query or scope.is_empty:
        return []

    tokens = _tokenize(query)
    if not tokens:
        return []

    ngrams = set(_extract_ngrams(tokens))
    query_token_set = set(tokens)
    clean_query = unicodedata.normalize("NFC", query).lower()

    # 1. Fetch active, ready resources in authorized scope
    try:
        res_qs = Resource.objects.filter(
            library_id__in=scope.authorized_library_ids,
            status=ResourceStatus.READY,
            processing_runs__is_active=True,
            processing_runs__status=ProcessingStatus.READY,
        ).distinct()

        if scope.authorized_resource_ids is not None:
            res_qs = res_qs.filter(id__in=scope.authorized_resource_ids)

        resources = list(res_qs)
    except Exception:
        return []

    if not resources:
        return []

    if len(resources) == 1:
        r = resources[0]
        return [
            ResourceCandidate(
                resource_id=r.id,
                resource_name=r.name,
                score=1.0,
                matched_signals=("Single authorized resource in scope",),
            )
        ]

    # 2. Batch fetch structural headings (level <= 2) across all candidate resources
    try:
        headings = list(
            DocumentStructureNode.objects.filter(
                resource_id__in=[r.id for r in resources],
                level__lte=2,
                processing_run__is_active=True,
                processing_run__status=ProcessingStatus.READY,
            ).values("resource_id", "level", "title", "normalized_title")
        )
    except Exception:
        headings = []

    headings_by_resource: dict[uuid.UUID, list[dict]] = {}
    for h in headings:
        headings_by_resource.setdefault(h["resource_id"], []).append(h)

    scored_list: list[ResourceCandidate] = []

    for r in resources:
        score = 0.0
        signals: list[str] = []

        res_name_norm = unicodedata.normalize("NFC", r.name).lower()
        res_tokens = _tokenize(r.name)
        res_token_set = set(res_tokens)

        # Priority 1: Exact query phrase match in resource title
        for ng in ngrams:
            if ng in res_name_norm:
                score += 10.0
                signals.append(f"Title contains phrase '{ng}'")

        # Priority 2: Token overlap with resource title
        common_title_tokens = query_token_set.intersection(res_token_set)
        for t in common_title_tokens:
            if len(t) >= 4:
                score += 4.0
                signals.append(f"Title matches token '{t}'")
            elif len(t) >= 3:
                score += 2.0

        # Priority 3 & 4: Structural heading matches (level 1 chapters and level 2 sections)
        r_headings = headings_by_resource.get(r.id, [])
        for h in r_headings:
            h_level = h.get("level", 1)
            h_title = h.get("normalized_title") or h.get("title", "")
            h_norm = unicodedata.normalize("NFC", h_title).lower()
            h_tokens = _tokenize(h_title)
            h_token_set = set(h_tokens)

            weight_mult = 1.0 if h_level == 1 else 0.7

            for ng in ngrams:
                if ng in h_norm:
                    pts = round(6.0 * weight_mult, 1)
                    score += pts
                    signals.append(f"L{h_level} heading '{h_title}' contains phrase '{ng}' (+{pts})")

            common_h_tokens = query_token_set.intersection(h_token_set)
            if len(common_h_tokens) >= 2:
                pts = round(len(common_h_tokens) * 3.0 * weight_mult, 1)
                score += pts
                signals.append(f"L{h_level} heading '{h_title}' matches tokens {common_h_tokens} (+{pts})")
            elif len(common_h_tokens) == 1:
                tok = next(iter(common_h_tokens))
                if len(tok) >= 4:
                    pts = round(2.0 * weight_mult, 1)
                    score += pts

        scored_list.append(
            ResourceCandidate(
                resource_id=r.id,
                resource_name=r.name,
                score=round(score, 2),
                matched_signals=tuple(signals),
            )
        )

    scored_list.sort(key=lambda s: s.score, reverse=True)
    return scored_list


def find_candidate_resources(
    query: str,
    scope: EffectiveRetrievalScope,
) -> ResourcePriorResult:
    """Identify and prioritize candidate resources within authorized scope as a retrieval prior.

    Selection Rules:
    - Retains top 1–3 relevant resources.
    - If top score < 3.0: weak/no evidence -> fallback to all resources (is_scope_restricted=False).
    - If top score >= 3.0: selects resources with score >= max(3.0, 0.65 * top_score).
    - Never permanently excludes resources (Level 4 global backfill preserves recall).
    """
    ranked = rank_candidate_resources(query, scope)
    if not ranked:
        return ResourcePriorResult(
            prioritized_resource_ids=(),
            all_scored_resources=(),
            confidence=0.0,
            is_scope_restricted=False,
        )

    if len(ranked) == 1:
        return ResourcePriorResult(
            prioritized_resource_ids=(ranked[0].resource_id,),
            all_scored_resources=tuple(ranked),
            confidence=1.0,
            is_scope_restricted=False,
        )

    top_score = ranked[0].score

    if top_score < 3.0:
        return ResourcePriorResult(
            prioritized_resource_ids=tuple(r.resource_id for r in ranked),
            all_scored_resources=tuple(ranked),
            confidence=0.0,
            is_scope_restricted=False,
        )

    threshold = max(3.0, top_score * 0.65)
    selected = [r for r in ranked if r.score >= threshold][:3]

    confidence = min(1.0, round(top_score / 15.0, 2))
    is_restricted = len(selected) < len(ranked)

    return ResourcePriorResult(
        prioritized_resource_ids=tuple(s.resource_id for s in selected),
        all_scored_resources=tuple(ranked),
        confidence=confidence,
        is_scope_restricted=is_restricted,
    )
