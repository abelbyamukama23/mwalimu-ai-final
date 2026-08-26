"""Context resolution engine for Mwalimu platform.

Determines and retrieves the bounded, relevant pedagogical context
for an execution run based on explicit geography, user familiarity,
institution focus, and controlled upward hierarchy expansion.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence

from django.db import models
from django.utils import timezone

from platform_api.apps.context.models import (
    ContextResource,
    ContextResourceStatus,
    ContextScopeType,
    GeographicUnit,
    GeographicUnitStatus,
    InstitutionContextRegion,
    UserFamiliarRegion,
    normalize_tags,
)
from platform_api.apps.context.resolution.dto import (
    ExplicitGeographicIntent,
    ResolvedContext,
    ResolvedContextItem,
)
from platform_api.apps.context.resolution.geographic_intent import (
    detect_geographic_intent,
)
from platform_api.apps.context.resolution.pedagogical_signal import (
    detect_pedagogical_signal,
)
from platform_api.apps.institutions.models import Institution
from platform_api.apps.memberships.models import Membership, MembershipStatus
from platform_api.apps.users.models import User


class ContextResolver:
    """Deterministic, bounded, explainable pedagogical context resolver."""

    def resolve(
        self,
        user: User,
        prompt: str,
        institution: Institution | uuid.UUID | str | None = None,
        subjects: Sequence[str] | None = None,
        topics: Sequence[str] | None = None,
        purposes: Sequence[str] | None = None,
        budget_limit: int = 5,
    ) -> ResolvedContext:
        """Resolve relevant pedagogical context for a prompt and user session."""
        if budget_limit < 1:
            budget_limit = 5

        # 1. Explicit geographic intent detection
        explicit_intent: ExplicitGeographicIntent | None = detect_geographic_intent(
            prompt
        )

        # 2. Pedagogical signal detection
        signal = detect_pedagogical_signal(
            prompt=prompt,
            explicit_intent=explicit_intent,
            subjects=subjects,
            topics=topics,
            purposes=purposes,
        )

        # Invariant: If not pedagogically context-relevant, return empty immediately
        if not signal.context_relevant:
            return ResolvedContext.empty(
                explanation=signal.reason,
                budget_limit=budget_limit,
            )

        # 3. Resolve and authorize active institution
        active_institution_id = self._resolve_active_institution(
            user=user, institution=institution
        )

        # 4. Determine candidate target geographic units
        familiar_considered = False
        institution_considered = False
        candidate_targets: list[tuple[uuid.UUID, str, str]] = []
        anchor_unit: GeographicUnit | None = None

        if explicit_intent is not None:
            try:
                unit = GeographicUnit.objects.get(
                    id=explicit_intent.geographic_unit_id,
                    status=GeographicUnitStatus.ACTIVE,
                )
                candidate_targets.append(
                    (
                        unit.id,
                        unit.name,
                        f"Explicitly requested location '{explicit_intent.unit_name}'.",
                    )
                )
                anchor_unit = unit
            except GeographicUnit.DoesNotExist:
                pass
        else:
            # Query user familiar regions ordered by priority
            ufr_list = list(
                UserFamiliarRegion.objects.filter(
                    user=user,
                    geographic_unit__status=GeographicUnitStatus.ACTIVE,
                )
                .select_related("geographic_unit")
                .order_by("priority", "-created_at")
            )

            if ufr_list:
                familiar_considered = True
                anchor_unit = ufr_list[0].geographic_unit
                for ufr in ufr_list:
                    candidate_targets.append(
                        (
                            ufr.geographic_unit.id,
                            ufr.geographic_unit.name,
                            (
                                f"Matched user's priority-{ufr.priority} "
                                f"familiar region ({ufr.geographic_unit.name})."
                            ),
                        )
                    )
            elif active_institution_id is not None:
                # Fallback to institution context regions
                icr_list = list(
                    InstitutionContextRegion.objects.filter(
                        institution_id=active_institution_id,
                        geographic_unit__status=GeographicUnitStatus.ACTIVE,
                    )
                    .select_related("geographic_unit")
                    .order_by("priority", "-created_at")
                )
                if icr_list:
                    institution_considered = True
                    anchor_unit = icr_list[0].geographic_unit
                    for icr in icr_list:
                        candidate_targets.append(
                            (
                                icr.geographic_unit.id,
                                icr.geographic_unit.name,
                                (
                                    f"Matched institution context region "
                                    f"({icr.geographic_unit.name})."
                                ),
                            )
                        )

        # 5. Base resource queryset with strict tenant scoping
        base_query = ContextResource.objects.filter(
            status=ContextResourceStatus.ACTIVE,
            geographic_unit__status=GeographicUnitStatus.ACTIVE,
        )

        if active_institution_id is not None:
            scope_filter = models.Q(scope_type=ContextScopeType.PLATFORM) | models.Q(
                scope_type=ContextScopeType.INSTITUTION,
                institution_id=active_institution_id,
            )
        else:
            scope_filter = models.Q(scope_type=ContextScopeType.PLATFORM)

        base_query = base_query.filter(scope_filter).select_related(
            "geographic_unit", "context_domain", "institution"
        )

        # 6. Retrieve and rank resources across candidate units
        selected_items: list[ResolvedContextItem] = []
        selected_ids: set[uuid.UUID] = set()
        selected_unit_ids: list[uuid.UUID] = []
        total_candidates = 0

        norm_subjects = normalize_tags(list(subjects or []))
        norm_topics = normalize_tags(list(topics or []))
        norm_purposes = normalize_tags(list(purposes or []))

        for unit_id, _unit_name, reason in candidate_targets:
            if len(selected_items) >= budget_limit:
                break

            unit_resources = list(base_query.filter(geographic_unit_id=unit_id))
            total_candidates += len(unit_resources)

            ranked = self._rank_resources(
                resources=unit_resources,
                prompt=prompt,
                subjects=norm_subjects,
                topics=norm_topics,
                purposes=norm_purposes,
            )

            for res in ranked:
                if res.id not in selected_ids:
                    selected_ids.add(res.id)
                    if res.geographic_unit_id not in selected_unit_ids:
                        selected_unit_ids.append(res.geographic_unit_id)
                    selected_items.append(self._to_item(res, selection_reason=reason))
                    if len(selected_items) >= budget_limit:
                        break

        # 7. Controlled upward geographic expansion if budget not satisfied
        expansion_occurred = False
        expansion_levels = 0

        if len(selected_items) < budget_limit and anchor_unit is not None:
            current_parent = anchor_unit.parent
            while current_parent is not None and len(selected_items) < budget_limit:
                if current_parent.status != GeographicUnitStatus.ACTIVE:
                    break

                expansion_occurred = True
                expansion_levels += 1
                expansion_reason = (
                    f"Expanded from {anchor_unit.name} to parent "
                    f"{current_parent.name} due to insufficient local context."
                )

                parent_resources = list(
                    base_query.filter(geographic_unit_id=current_parent.id)
                )
                total_candidates += len(parent_resources)

                ranked_parent = self._rank_resources(
                    resources=parent_resources,
                    prompt=prompt,
                    subjects=norm_subjects,
                    topics=norm_topics,
                    purposes=norm_purposes,
                )

                for res in ranked_parent:
                    if res.id not in selected_ids:
                        selected_ids.add(res.id)
                        if res.geographic_unit_id not in selected_unit_ids:
                            selected_unit_ids.append(res.geographic_unit_id)
                        selected_items.append(
                            self._to_item(res, selection_reason=expansion_reason)
                        )
                        if len(selected_items) >= budget_limit:
                            break

                current_parent = current_parent.parent

        # 8. Assemble structured result
        explanation = (
            f"Resolved {len(selected_items)} contextual item(s) for '{signal.reason}'."
        )

        return ResolvedContext(
            context_considered=True,
            explicit_geographic_intent=(
                explicit_intent.unit_name if explicit_intent else None
            ),
            familiar_regions_considered=familiar_considered,
            institution_regions_considered=institution_considered,
            selected_geographic_unit_ids=selected_unit_ids,
            geographic_expansion_occurred=expansion_occurred,
            expansion_levels=expansion_levels,
            total_candidate_resources=total_candidates,
            budget_limit=budget_limit,
            items=selected_items,
            explanation=explanation,
            resolved_at=timezone.now().isoformat(),
        )

    def _resolve_active_institution(
        self,
        user: User,
        institution: Institution | uuid.UUID | str | None,
    ) -> uuid.UUID | None:
        """Verify active membership before authorizing institutional scope."""
        if institution is None:
            return None

        if isinstance(institution, Institution):
            inst_id = institution.id
        else:
            try:
                inst_id = uuid.UUID(str(institution))
            except (ValueError, TypeError):
                return None

        if user.is_superuser:
            return inst_id

        is_member = Membership.objects.filter(
            user=user,
            institution_id=inst_id,
            status=MembershipStatus.ACTIVE,
        ).exists()

        return inst_id if is_member else None

    def _rank_resources(
        self,
        resources: list[ContextResource],
        prompt: str,
        subjects: list[str],
        topics: list[str],
        purposes: list[str],
    ) -> list[ContextResource]:
        """Rank resources deterministically by relevance score, timestamp, and ID."""
        lower_prompt = prompt.lower()

        def score_resource(r: ContextResource) -> tuple[int, float, str]:
            score = 0
            # 1. Subject match
            for s in r.applicable_subjects:
                if s in subjects or s in lower_prompt:
                    score += 15

            # 2. Topic match
            for t in r.applicable_topics:
                if t in topics or t in lower_prompt:
                    score += 20

            # 3. Purpose match
            for p in r.pedagogical_purposes:
                if p in purposes or p in lower_prompt:
                    score += 10

            # 4. Domain name/description match
            if r.context_domain.slug in lower_prompt:
                score += 5

            # 5. Keyword match in title/content
            words = set(re.findall(r"\w{4,}", lower_prompt))
            title_words = set(re.findall(r"\w{4,}", r.title.lower()))
            score += len(words & title_words) * 3

            # Return tuple for deterministic sorting: (-score, -timestamp, uuid_str)
            timestamp = r.created_at.timestamp()
            return (score, timestamp, str(r.id))

        return sorted(resources, key=score_resource, reverse=True)

    def _to_item(
        self, resource: ContextResource, selection_reason: str
    ) -> ResolvedContextItem:
        """Convert a ContextResource model to a ResolvedContextItem DTO."""
        return ResolvedContextItem(
            resource_id=resource.id,
            geographic_unit_id=resource.geographic_unit.id,
            geographic_unit_name=resource.geographic_unit.name,
            geographic_unit_type=resource.geographic_unit.unit_type,
            context_domain=resource.context_domain.name,
            title=resource.title,
            content=resource.content,
            applicable_subjects=resource.applicable_subjects,
            applicable_topics=resource.applicable_topics,
            pedagogical_purposes=resource.pedagogical_purposes,
            source_type=resource.scope_type,
            selection_reason=selection_reason,
        )
