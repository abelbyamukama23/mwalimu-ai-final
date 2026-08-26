"""Unit and integration tests for the Mwalimu Context Resolution Engine."""

from __future__ import annotations

import pytest

from platform_api.apps.context.models import (
    ContextDomain,
    ContextResource,
    ContextResourceStatus,
    ContextScopeType,
    GeographicUnit,
    GeographicUnitStatus,
    GeographicUnitType,
    InstitutionContextRegion,
    UserFamiliarRegion,
)
from platform_api.apps.context.resolution.dto import (
    ExplicitGeographicIntent,
)
from platform_api.apps.context.resolution.geographic_intent import (
    detect_geographic_intent,
)
from platform_api.apps.context.resolution.pedagogical_signal import (
    detect_pedagogical_signal,
)
from platform_api.apps.context.resolution.resolver import ContextResolver
from platform_api.apps.institutions.models import Institution
from platform_api.apps.memberships.models import (
    Membership,
)
from platform_api.apps.users.models import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def country_uganda(db: None) -> GeographicUnit:
    """Return Uganda country unit."""
    return GeographicUnit.objects.create(
        name="Uganda",
        slug="uganda",
        unit_type=GeographicUnitType.COUNTRY,
        country_code="UG",
        status=GeographicUnitStatus.ACTIVE,
    )


@pytest.fixture
def region_western(db: None, country_uganda: GeographicUnit) -> GeographicUnit:
    """Return Western Region under Uganda."""
    return GeographicUnit.objects.create(
        name="Western Region",
        slug="western-region",
        unit_type=GeographicUnitType.REGION,
        parent=country_uganda,
        country_code="UG",
        status=GeographicUnitStatus.ACTIVE,
    )


@pytest.fixture
def district_kyenjojo(db: None, region_western: GeographicUnit) -> GeographicUnit:
    """Return Kyenjojo District under Western Region."""
    return GeographicUnit.objects.create(
        name="Kyenjojo District",
        slug="kyenjojo",
        unit_type=GeographicUnitType.DISTRICT,
        parent=region_western,
        country_code="UG",
        status=GeographicUnitStatus.ACTIVE,
        metadata={"aliases": ["Kyenjojo"]},
    )


@pytest.fixture
def district_kampala(db: None, country_uganda: GeographicUnit) -> GeographicUnit:
    """Return Kampala District under Uganda."""
    return GeographicUnit.objects.create(
        name="Kampala District",
        slug="kampala",
        unit_type=GeographicUnitType.DISTRICT,
        parent=country_uganda,
        country_code="UG",
        status=GeographicUnitStatus.ACTIVE,
        metadata={"aliases": ["Kampala"]},
    )


@pytest.fixture
def district_jinja(db: None, country_uganda: GeographicUnit) -> GeographicUnit:
    """Return Jinja District under Uganda."""
    return GeographicUnit.objects.create(
        name="Jinja District",
        slug="jinja",
        unit_type=GeographicUnitType.DISTRICT,
        parent=country_uganda,
        country_code="UG",
        status=GeographicUnitStatus.ACTIVE,
        metadata={"aliases": ["Jinja"]},
    )


@pytest.fixture
def archived_unit(db: None, country_uganda: GeographicUnit) -> GeographicUnit:
    """Return an archived unit."""
    return GeographicUnit.objects.create(
        name="Old Territory",
        slug="old-territory",
        unit_type=GeographicUnitType.DISTRICT,
        parent=country_uganda,
        country_code="UG",
        status=GeographicUnitStatus.ARCHIVED,
    )


@pytest.fixture
def domain_agriculture(db: None) -> ContextDomain:
    """Return Agriculture domain."""
    return ContextDomain.objects.create(
        name="Agriculture & Farming",
        slug="agriculture",
        description="Farming practices and crops.",
    )


@pytest.fixture
def domain_climate(db: None) -> ContextDomain:
    """Return Climate domain."""
    return ContextDomain.objects.create(
        name="Climate & Environment",
        slug="climate",
        description="Weather, rainfall, topography.",
    )


@pytest.fixture
def resolver() -> ContextResolver:
    """Return ContextResolver instance."""
    return ContextResolver()


# ---------------------------------------------------------------------------
# 1. Geographic Intent Detector Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGeographicIntentDetector:
    """Tests for detecting explicit geographic locations in prompts."""

    def test_detect_explicit_name_in_prompt(
        self, district_kyenjojo: GeographicUnit
    ) -> None:
        """Detect explicit mention of Kyenjojo."""
        intent = detect_geographic_intent("Explain soil erosion in Kyenjojo please.")
        assert intent is not None
        assert intent.geographic_unit_id == district_kyenjojo.id
        assert intent.unit_name == "Kyenjojo District"
        assert intent.matched_text.lower() == "kyenjojo"

    def test_detect_multi_word_location(self, region_western: GeographicUnit) -> None:
        """Detect multi-word location 'Western Region'."""
        intent = detect_geographic_intent("What is the climate of Western Region?")
        assert intent is not None
        assert intent.geographic_unit_id == region_western.id
        assert intent.unit_name == "Western Region"

    def test_avoid_partial_word_false_positive(
        self, country_uganda: GeographicUnit
    ) -> None:
        """Partial substrings inside words do not trigger false positive matches."""
        intent = detect_geographic_intent("Debugging a software problem.")
        assert intent is None

    def test_no_geographic_mention_returns_none(
        self, country_uganda: GeographicUnit
    ) -> None:
        """Prompts without geographic mentions return None."""
        intent = detect_geographic_intent("What is photosynthesis in plants?")
        assert intent is None


# ---------------------------------------------------------------------------
# 2. Pedagogical Signal Detector Tests
# ---------------------------------------------------------------------------


class TestPedagogicalSignalDetector:
    """Tests for determining pedagogical context relevance."""

    def test_abstract_math_not_relevant(self) -> None:
        """Abstract math question has no contextual relevance."""
        signal = detect_pedagogical_signal("Solve for x: 3x + 5 = 20")
        assert not signal.context_relevant

    def test_abstract_chemistry_not_relevant(self) -> None:
        """Abstract science question has no contextual relevance."""
        signal = detect_pedagogical_signal("What is the chemical formula of water?")
        assert not signal.context_relevant

    def test_locality_phrasing_triggers_relevance(self) -> None:
        """Phrases like 'from my area' trigger relevance."""
        signal = detect_pedagogical_signal(
            "Explain soil erosion using an example from my area."
        )
        assert signal.context_relevant
        assert "from my area" in signal.detected_terms

    def test_domain_vocabulary_triggers_relevance(self) -> None:
        """Terms like 'coffee farming' or 'soil erosion' trigger relevance."""
        signal = detect_pedagogical_signal(
            "How do farmers prevent soil erosion during the rainy season?"
        )
        assert signal.context_relevant
        assert "soil erosion" in signal.detected_terms

    def test_explicit_geographic_intent_triggers_relevance(self) -> None:
        """Explicit location reference automatically triggers relevance."""
        intent = ExplicitGeographicIntent(
            geographic_unit_id=pytest.importorskip("uuid").uuid4(),
            unit_name="Kyenjojo District",
            unit_type="district",
            matched_text="Kyenjojo",
            reason="Matched location.",
        )
        signal = detect_pedagogical_signal(
            "Tell me about farming in Kyenjojo.",
            explicit_intent=intent,
        )
        assert signal.context_relevant
        assert signal.explicit_geography_detected


# ---------------------------------------------------------------------------
# 3. Context Resolver Engine Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestContextResolverEngine:
    """Comprehensive tests for the ContextResolver resolution pipeline."""

    def test_context_not_relevant_returns_empty_result(
        self,
        resolver: ContextResolver,
        user_a: User,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """If context is not relevant, returns empty ResolvedContext immediately."""
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )
        result = resolver.resolve(
            user=user_a,
            prompt="What is the atomic number of carbon?",
        )
        assert not result.context_considered
        assert len(result.items) == 0
        assert (
            "not deemed pedagogically relevant" in result.explanation
            or "No geographic" in result.explanation
        )

    def test_explicit_geographic_location_overrides_familiarity(
        self,
        resolver: ContextResolver,
        user_a: User,
        district_kyenjojo: GeographicUnit,
        district_kampala: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Explicit prompt location Kyenjojo overrides user's familiar region."""
        # User familiar region is Kampala
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kampala, priority=1
        )
        # Resources for both
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Kyenjojo Tea Farming",
            content="Volcanic soils in Kyenjojo.",
            scope_type=ContextScopeType.PLATFORM,
        )
        ContextResource.objects.create(
            geographic_unit=district_kampala,
            context_domain=domain_agriculture,
            title="Urban Farming in Kampala",
            content="Hydroponics in Kampala.",
            scope_type=ContextScopeType.PLATFORM,
        )

        result = resolver.resolve(
            user=user_a,
            prompt="Explain agriculture in Kyenjojo using tea estates.",
        )
        assert result.context_considered
        assert result.explicit_geographic_intent == "Kyenjojo District"
        assert len(result.items) == 1
        assert result.items[0].title == "Kyenjojo Tea Farming"
        assert "Explicitly requested" in result.items[0].selection_reason

    def test_user_familiar_region_priority_order_respected(
        self,
        resolver: ContextResolver,
        user_a: User,
        district_kyenjojo: GeographicUnit,
        district_kampala: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Priority 1 familiar region is queried before Priority 2."""
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kampala, priority=2
        )

        # 3 resources for Kyenjojo, 3 for Kampala
        for i in range(3):
            ContextResource.objects.create(
                geographic_unit=district_kyenjojo,
                context_domain=domain_agriculture,
                title=f"Kyenjojo Crop {i}",
                content=f"Content {i}",
                scope_type=ContextScopeType.PLATFORM,
            )
            ContextResource.objects.create(
                geographic_unit=district_kampala,
                context_domain=domain_agriculture,
                title=f"Kampala Crop {i}",
                content=f"Content {i}",
                scope_type=ContextScopeType.PLATFORM,
            )

        # Request with budget limit 2
        result = resolver.resolve(
            user=user_a,
            prompt="Give me local examples of farming practices in my area.",
            budget_limit=2,
        )
        assert result.context_considered
        assert result.familiar_regions_considered
        assert len(result.items) == 2
        # Both should come from priority-1 (Kyenjojo)
        for item in result.items:
            assert "Kyenjojo" in item.geographic_unit_name
            assert "priority-1" in item.selection_reason

    def test_multiple_familiar_regions_evaluated_before_upward_expansion(
        self,
        resolver: ContextResolver,
        user_a: User,
        district_kyenjojo: GeographicUnit,
        district_kampala: GeographicUnit,
        region_western: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Priority 2 familiar region is evaluated before ascending parent hierarchy."""
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kampala, priority=2
        )

        # Kyenjojo has 1 item, Kampala has 2 items, Western Region (parent) has 5 items
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Kyenjojo Farming",
            content="Local Kyenjojo content.",
            scope_type=ContextScopeType.PLATFORM,
        )
        ContextResource.objects.create(
            geographic_unit=district_kampala,
            context_domain=domain_agriculture,
            title="Kampala Farming",
            content="Local Kampala content.",
            scope_type=ContextScopeType.PLATFORM,
        )
        ContextResource.objects.create(
            geographic_unit=region_western,
            context_domain=domain_agriculture,
            title="Western Region Overview",
            content="Regional western content.",
            scope_type=ContextScopeType.PLATFORM,
        )

        # Budget is 2: should take 1 from Kyenjojo (pri 1) and 1 from Kampala (pri 2)
        # and NOT expand to Western Region!
        result = resolver.resolve(
            user=user_a,
            prompt="Give me local examples of farming in my area.",
            budget_limit=2,
        )
        assert len(result.items) == 2
        titles = [item.title for item in result.items]
        assert "Kyenjojo Farming" in titles
        assert "Kampala Farming" in titles
        assert "Western Region Overview" not in titles
        assert not result.geographic_expansion_occurred

    def test_controlled_upward_geographic_expansion(
        self,
        resolver: ContextResolver,
        user_a: User,
        district_kyenjojo: GeographicUnit,
        region_western: GeographicUnit,
        country_uganda: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Resolver expands upward to parent hierarchy when local context is low."""
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )

        # Only 1 item in Kyenjojo, 2 in Western Region, 2 in Uganda
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Kyenjojo Tea",
            content="Content",
            scope_type=ContextScopeType.PLATFORM,
        )
        ContextResource.objects.create(
            geographic_unit=region_western,
            context_domain=domain_agriculture,
            title="Western Dairy Farming",
            content="Content",
            scope_type=ContextScopeType.PLATFORM,
        )
        ContextResource.objects.create(
            geographic_unit=country_uganda,
            context_domain=domain_agriculture,
            title="Uganda Coffee Export",
            content="Content",
            scope_type=ContextScopeType.PLATFORM,
        )

        result = resolver.resolve(
            user=user_a,
            prompt="Explain farming practices in my area.",
            budget_limit=3,
        )
        assert len(result.items) == 3
        assert result.geographic_expansion_occurred
        assert result.expansion_levels >= 1
        titles = [item.title for item in result.items]
        assert "Kyenjojo Tea" in titles
        assert "Western Dairy Farming" in titles
        assert "Uganda Coffee Export" in titles

    def test_institution_context_region_fallback(
        self,
        resolver: ContextResolver,
        user_a: User,
        membership_a: Membership,
        institution_a: Institution,
        district_jinja: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """User with no familiar regions falls back to institution focus region."""
        # User has no familiar regions configured
        # Institution A has Jinja as focus region
        InstitutionContextRegion.objects.create(
            institution=institution_a,
            geographic_unit=district_jinja,
            priority=1,
        )
        ContextResource.objects.create(
            geographic_unit=district_jinja,
            context_domain=domain_agriculture,
            title="Jinja Sugarcane Farming",
            content="Kakira sugarcane estates in Jinja.",
            scope_type=ContextScopeType.PLATFORM,
        )

        result = resolver.resolve(
            user=user_a,
            prompt="Explain agriculture in our region.",
            institution=institution_a,
            budget_limit=3,
        )
        assert result.context_considered
        assert result.institution_regions_considered
        assert len(result.items) == 1
        assert result.items[0].title == "Jinja Sugarcane Farming"
        assert "institution context region" in result.items[0].selection_reason

    def test_cross_institution_resources_never_returned(
        self,
        resolver: ContextResolver,
        user_a: User,
        membership_a: Membership,
        institution_a: Institution,
        institution_b: Institution,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """User in Inst A never receives Inst B private context resources."""
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )
        # Institution A resource
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Institution A Farming Project",
            content="Private school farm.",
            scope_type=ContextScopeType.INSTITUTION,
            institution=institution_a,
        )
        # Institution B resource
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Institution B Secret Project",
            content="Institution B secret farm.",
            scope_type=ContextScopeType.INSTITUTION,
            institution=institution_b,
        )

        result = resolver.resolve(
            user=user_a,
            prompt="Give me local farming examples in my area.",
            institution=institution_a,
        )
        titles = [item.title for item in result.items]
        assert "Institution A Farming Project" in titles
        assert "Institution B Secret Project" not in titles

    def test_archived_resources_and_units_ignored(
        self,
        resolver: ContextResolver,
        user_a: User,
        district_kyenjojo: GeographicUnit,
        archived_unit: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Archived context resources and units are excluded from resolution."""
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )
        # Active resource
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Active Resource",
            content="Active content.",
            scope_type=ContextScopeType.PLATFORM,
            status=ContextResourceStatus.ACTIVE,
        )
        # Archived resource on active unit
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Archived Resource",
            content="Archived content.",
            scope_type=ContextScopeType.PLATFORM,
            status=ContextResourceStatus.ARCHIVED,
        )

        result = resolver.resolve(
            user=user_a,
            prompt="Give me local farming examples in my area.",
        )
        titles = [item.title for item in result.items]
        assert "Active Resource" in titles
        assert "Archived Resource" not in titles

    def test_pedagogical_tag_scoring_ranks_relevant_resources_higher(
        self,
        resolver: ContextResolver,
        user_a: User,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Resources matching requested subjects and topics rank higher."""
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )
        # High relevance resource
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Tea Photosynthesis and Soil",
            content="Photosynthesis in tea plants in volcanic soils.",
            scope_type=ContextScopeType.PLATFORM,
            applicable_subjects=["biology", "agriculture"],
            applicable_topics=["photosynthesis"],
            pedagogical_purposes=["example"],
        )
        # Lower relevance resource
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="General Livestock Cattle",
            content="Cattle keeping.",
            scope_type=ContextScopeType.PLATFORM,
            applicable_subjects=["social studies"],
            applicable_topics=["pastoralism"],
            pedagogical_purposes=["explanation"],
        )

        result = resolver.resolve(
            user=user_a,
            prompt="Explain photosynthesis using a local farming example in my area.",
            subjects=["biology"],
            topics=["photosynthesis"],
            purposes=["example"],
            budget_limit=1,
        )
        assert len(result.items) == 1
        assert result.items[0].title == "Tea Photosynthesis and Soil"

    def test_deterministic_resolution(
        self,
        resolver: ContextResolver,
        user_a: User,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Resolution with identical input produces deterministic identical output."""
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )
        for i in range(3):
            ContextResource.objects.create(
                geographic_unit=district_kyenjojo,
                context_domain=domain_agriculture,
                title=f"Farming Item {i}",
                content=f"Farming content {i}",
                scope_type=ContextScopeType.PLATFORM,
            )

        res1 = resolver.resolve(user=user_a, prompt="Explain farming in my area.")
        res2 = resolver.resolve(user=user_a, prompt="Explain farming in my area.")

        assert [item.resource_id for item in res1.items] == [
            item.resource_id for item in res2.items
        ]
        assert [item.title for item in res1.items] == [
            item.title for item in res2.items
        ]

    def test_unauthorized_institution_dropped_safely(
        self,
        resolver: ContextResolver,
        user_a: User,
        institution_b: Institution,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """If client provides foreign institution where user is not member, dropped."""
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Institution B Private Farm",
            content="Private snippet.",
            scope_type=ContextScopeType.INSTITUTION,
            institution=institution_b,
        )
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Platform Public Farm",
            content="Public snippet.",
            scope_type=ContextScopeType.PLATFORM,
        )

        # User A supplies Institution B, but is NOT a member of Institution B
        result = resolver.resolve(
            user=user_a,
            prompt="Explain farming in my area.",
            institution=institution_b,
        )
        titles = [item.title for item in result.items]
        assert "Platform Public Farm" in titles
        assert "Institution B Private Farm" not in titles

    def test_user_without_familiar_regions_or_institution(
        self,
        resolver: ContextResolver,
        user_a: User,
        country_uganda: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """User with no preferences receives platform context on explicit request."""
        ContextResource.objects.create(
            geographic_unit=country_uganda,
            context_domain=domain_agriculture,
            title="National Agriculture Policy",
            content="Uganda agricultural framework.",
            scope_type=ContextScopeType.PLATFORM,
        )
        result = resolver.resolve(
            user=user_a,
            prompt="Explain agriculture in Uganda.",
        )
        assert result.context_considered
        assert len(result.items) == 1
        assert result.items[0].title == "National Agriculture Policy"

    def test_budget_limit_strictly_enforced(
        self,
        resolver: ContextResolver,
        user_a: User,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Strictly enforces maximum items returned to match budget limit."""
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )
        for i in range(8):
            ContextResource.objects.create(
                geographic_unit=district_kyenjojo,
                context_domain=domain_agriculture,
                title=f"Resource {i}",
                content=f"Content {i}",
                scope_type=ContextScopeType.PLATFORM,
            )
        result = resolver.resolve(
            user=user_a,
            prompt="Explain local farming in my area.",
            budget_limit=4,
        )
        assert len(result.items) == 4
        assert result.budget_limit == 4

    def test_dto_serialization(
        self,
        resolver: ContextResolver,
        user_a: User,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """ResolvedContext and ResolvedContextItem serialize cleanly to dictionaries."""
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Kyenjojo Tea Overview",
            content="Content.",
            scope_type=ContextScopeType.PLATFORM,
        )
        result = resolver.resolve(
            user=user_a,
            prompt="Explain tea farming in my area.",
        )
        data = result.to_dict()
        assert data["context_considered"] is True
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Kyenjojo Tea Overview"
        assert "resource_id" in data["items"][0]
