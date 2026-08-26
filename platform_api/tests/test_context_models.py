"""Model tests for the Mwalimu context domain."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError

from platform_api.apps.context.models import (
    ContextDomain,
    ContextResource,
    ContextResourceStatus,
    ContextScopeType,
    GeographicUnit,
    GeographicUnitStatus,
    GeographicUnitType,
    InstitutionContextRegion,
    PedagogicalPurpose,
    UserFamiliarRegion,
    normalize_tags,
)
from platform_api.apps.institutions.models import Institution
from platform_api.apps.users.models import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def country_uganda(db: None) -> GeographicUnit:
    """Return root country unit: Uganda."""
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
    )


@pytest.fixture
def domain_agriculture(db: None) -> ContextDomain:
    """Return Agriculture context domain."""
    return ContextDomain.objects.create(
        name="Agriculture & Farming",
        slug="agriculture",
        description="Farming practices, crops, livestock, and local agronomy.",
    )


# ---------------------------------------------------------------------------
# 1. GeographicUnit Model Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGeographicUnit:
    """Tests for GeographicUnit hierarchy, uniqueness, and protection constraints."""

    def test_create_root_unit(self, country_uganda: GeographicUnit) -> None:
        """Create a root geographic unit."""
        assert country_uganda.parent is None
        assert country_uganda.name == "Uganda"
        assert country_uganda.unit_type == GeographicUnitType.COUNTRY
        assert country_uganda.status == GeographicUnitStatus.ACTIVE
        assert "Uganda (country)" in str(country_uganda)

    def test_create_child_unit(
        self, country_uganda: GeographicUnit, region_western: GeographicUnit
    ) -> None:
        """Create a child unit under a parent."""
        assert region_western.parent == country_uganda
        assert region_western in country_uganda.children.all()
        assert "Western Region (region, in Uganda)" in str(region_western)

    def test_same_slug_allowed_under_different_parents(
        self, country_uganda: GeographicUnit
    ) -> None:
        """Identical slugs under different parents do not collide."""
        district_a = GeographicUnit.objects.create(
            name="District A",
            slug="district-a",
            unit_type=GeographicUnitType.DISTRICT,
            parent=country_uganda,
        )
        district_b = GeographicUnit.objects.create(
            name="District B",
            slug="district-b",
            unit_type=GeographicUnitType.DISTRICT,
            parent=country_uganda,
        )

        # Both have a subcounty with slug 'central'
        sub_a = GeographicUnit.objects.create(
            name="Central Subcounty",
            slug="central",
            unit_type=GeographicUnitType.SUBCOUNTY,
            parent=district_a,
        )
        sub_b = GeographicUnit.objects.create(
            name="Central Town Council",
            slug="central",
            unit_type=GeographicUnitType.SUBCOUNTY,
            parent=district_b,
        )
        assert sub_a.slug == sub_b.slug == "central"
        assert sub_a.parent != sub_b.parent

    def test_duplicate_slug_rejected_under_same_parent(
        self, region_western: GeographicUnit
    ) -> None:
        """Duplicate slug under the same parent raises an IntegrityError."""
        GeographicUnit.objects.create(
            name="Kyenjojo",
            slug="kyenjojo",
            unit_type=GeographicUnitType.DISTRICT,
            parent=region_western,
        )
        with pytest.raises(IntegrityError):
            GeographicUnit.objects.create(
                name="Kyenjojo Duplicate",
                slug="kyenjojo",
                unit_type=GeographicUnitType.DISTRICT,
                parent=region_western,
            )

    def test_duplicate_root_slug_rejected(self, country_uganda: GeographicUnit) -> None:
        """Duplicate root slug raises an IntegrityError."""
        with pytest.raises(IntegrityError):
            GeographicUnit.objects.create(
                name="Uganda Duplicate",
                slug="uganda",
                unit_type=GeographicUnitType.COUNTRY,
                parent=None,
            )

    def test_self_parent_rejected(self, country_uganda: GeographicUnit) -> None:
        """A unit cannot be its own parent."""
        country_uganda.parent = country_uganda
        with pytest.raises(ValidationError) as excinfo:
            country_uganda.clean()
        assert "cannot be its own parent" in str(excinfo.value)

    def test_hierarchy_cycle_rejected(
        self,
        country_uganda: GeographicUnit,
        region_western: GeographicUnit,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """A cyclical parent-child loop is detected and rejected."""
        # Cycle: Uganda -> Western -> Kyenjojo -> Uganda
        country_uganda.parent = district_kyenjojo
        with pytest.raises(ValidationError) as excinfo:
            country_uganda.clean()
        assert "Hierarchy cycle detected" in str(excinfo.value)

    def test_archived_status_works(self, country_uganda: GeographicUnit) -> None:
        """Archiving a unit saves and is queryable."""
        country_uganda.status = GeographicUnitStatus.ARCHIVED
        country_uganda.save()
        country_uganda.refresh_from_db()
        assert country_uganda.status == GeographicUnitStatus.ARCHIVED

    def test_protect_prevents_deletion_when_children_exist(
        self, country_uganda: GeographicUnit, region_western: GeographicUnit
    ) -> None:
        """Deleting a parent unit with children raises ProtectedError."""
        with pytest.raises(ProtectedError):
            country_uganda.delete()

    def test_protect_prevents_deletion_when_context_resource_references_it(
        self,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Deleting a unit referenced by a ContextResource raises ProtectedError."""
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Tea Farming in Kyenjojo",
            content="Tea is a major commercial crop grown across Kyenjojo.",
            scope_type=ContextScopeType.PLATFORM,
        )
        with pytest.raises(ProtectedError):
            district_kyenjojo.delete()


# ---------------------------------------------------------------------------
# 2. ContextDomain Model Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestContextDomain:
    """Tests for ContextDomain classification model."""

    def test_create_context_domain(self, domain_agriculture: ContextDomain) -> None:
        """Create a valid context domain."""
        assert domain_agriculture.name == "Agriculture & Farming"
        assert domain_agriculture.slug == "agriculture"
        assert str(domain_agriculture) == "Agriculture & Farming"

    def test_unique_name_enforced(self, domain_agriculture: ContextDomain) -> None:
        """Duplicate domain name raises IntegrityError."""
        with pytest.raises(IntegrityError):
            ContextDomain.objects.create(
                name="Agriculture & Farming",
                slug="agriculture-2",
            )

    def test_unique_slug_enforced(self, domain_agriculture: ContextDomain) -> None:
        """Duplicate domain slug raises IntegrityError."""
        with pytest.raises(IntegrityError):
            ContextDomain.objects.create(
                name="Another Agriculture",
                slug="agriculture",
            )


# ---------------------------------------------------------------------------
# 3. ContextResource Model Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestContextResource:
    """Tests for ContextResource pedagogical knowledge snippets."""

    def test_create_valid_platform_resource(
        self,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Create a valid platform-scoped context resource."""
        res = ContextResource(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Tea and Coffee Farming",
            content=(
                "Kyenjojo district has fertile volcanic soils supporting tea estates."
            ),
            scope_type=ContextScopeType.PLATFORM,
            applicable_subjects=["Biology", "Agriculture", "Geography"],
            applicable_topics=["Photosynthesis", "Cash Crops"],
            pedagogical_purposes=["example", "explanation"],
        )
        res.clean()
        res.save()

        assert res.scope_type == ContextScopeType.PLATFORM
        assert res.institution is None
        assert res.status == ContextResourceStatus.ACTIVE
        assert res.applicable_subjects == ["biology", "agriculture", "geography"]
        assert res.applicable_topics == ["photosynthesis", "cash crops"]
        assert res.pedagogical_purposes == ["example", "explanation"]
        assert str(res) == "Tea and Coffee Farming (Kyenjojo District)"

    def test_create_valid_institution_resource(
        self,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
        institution_a: Institution,
    ) -> None:
        """Create a valid institution-scoped context resource."""
        res = ContextResource(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="School Farm Irrigation",
            content="Our school farm utilizes gravity-fed drip irrigation.",
            scope_type=ContextScopeType.INSTITUTION,
            institution=institution_a,
            applicable_subjects=["Agriculture"],
            pedagogical_purposes=["activity"],
        )
        res.clean()
        res.save()

        assert res.scope_type == ContextScopeType.INSTITUTION
        assert res.institution == institution_a

    def test_platform_resource_cannot_specify_institution(
        self,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
        institution_a: Institution,
    ) -> None:
        """Platform-scoped resource must not be linked to an institution."""
        res = ContextResource(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Invalid Platform Resource",
            content="Content text.",
            scope_type=ContextScopeType.PLATFORM,
            institution=institution_a,
        )
        with pytest.raises(ValidationError) as excinfo:
            res.clean()
        assert "must not be linked to an institution" in str(excinfo.value)

        # Database CheckConstraint rejection
        with pytest.raises(IntegrityError):
            res.save()

    def test_institution_resource_must_specify_institution(
        self,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Institution-scoped resource must specify an institution."""
        res = ContextResource(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Invalid Institution Resource",
            content="Content text.",
            scope_type=ContextScopeType.INSTITUTION,
            institution=None,
        )
        with pytest.raises(ValidationError) as excinfo:
            res.clean()
        assert "must be linked to an institution" in str(excinfo.value)

        # Database CheckConstraint rejection
        with pytest.raises(IntegrityError):
            res.save()

    def test_content_length_limit_enforced(
        self,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Content exceeding 5000 characters is rejected."""
        res = ContextResource(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Overly Long Resource",
            content="A" * 5001,
            scope_type=ContextScopeType.PLATFORM,
        )
        with pytest.raises(ValidationError) as excinfo:
            res.clean()
        assert "cannot exceed 5000 characters" in str(excinfo.value)

    def test_invalid_pedagogical_purpose_rejected(
        self,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Invalid pedagogical purpose string is rejected."""
        res = ContextResource(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Invalid Purpose Resource",
            content="Sample text.",
            scope_type=ContextScopeType.PLATFORM,
            pedagogical_purposes=["example", "invalid_purpose_string"],
        )
        with pytest.raises(ValidationError) as excinfo:
            res.clean()
        assert "Invalid pedagogical purpose" in str(excinfo.value)

    def test_valid_pedagogical_purposes_accepted(
        self,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """All valid PedagogicalPurpose enum values are accepted."""
        all_purposes = [p.value for p in PedagogicalPurpose]
        res = ContextResource(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="All Purposes Resource",
            content="Sample text.",
            scope_type=ContextScopeType.PLATFORM,
            pedagogical_purposes=all_purposes,
        )
        res.clean()
        res.save()
        assert set(res.pedagogical_purposes) == set(all_purposes)

    def test_archived_geographic_unit_cannot_be_used_for_new_resource(
        self,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Attaching a context resource to an archived unit raises ValidationError."""
        district_kyenjojo.status = GeographicUnitStatus.ARCHIVED
        district_kyenjojo.save()

        res = ContextResource(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Archived Unit Context",
            content="Sample text.",
            scope_type=ContextScopeType.PLATFORM,
        )
        with pytest.raises(ValidationError) as excinfo:
            res.clean()
        assert "archived geographic unit" in str(excinfo.value)

    def test_domain_deletion_protection(
        self,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Deleting a domain with attached resources raises ProtectedError."""
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Resource Title",
            content="Content.",
            scope_type=ContextScopeType.PLATFORM,
        )
        with pytest.raises(ProtectedError):
            domain_agriculture.delete()


# ---------------------------------------------------------------------------
# 4. UserFamiliarRegion Model Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUserFamiliarRegion:
    """Tests for UserFamiliarRegion configuration."""

    def test_create_valid_user_familiar_region(
        self,
        user_a: User,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Create a valid user familiar region."""
        ufr = UserFamiliarRegion(
            user=user_a,
            geographic_unit=district_kyenjojo,
            priority=1,
        )
        ufr.clean()
        ufr.save()

        assert ufr.user == user_a
        assert ufr.geographic_unit == district_kyenjojo
        assert ufr.priority == 1
        assert "Priority 1" in str(ufr)

    def test_same_user_cannot_select_same_unit_twice(
        self,
        user_a: User,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """User cannot add the same geographic unit more than once."""
        UserFamiliarRegion.objects.create(
            user=user_a,
            geographic_unit=district_kyenjojo,
            priority=1,
        )
        with pytest.raises(IntegrityError):
            UserFamiliarRegion.objects.create(
                user=user_a,
                geographic_unit=district_kyenjojo,
                priority=2,
            )

    def test_different_users_can_select_same_unit(
        self,
        user_a: User,
        user_b: User,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Distinct users can configure the same geographic unit."""
        ufr_a = UserFamiliarRegion.objects.create(
            user=user_a,
            geographic_unit=district_kyenjojo,
            priority=1,
        )
        ufr_b = UserFamiliarRegion.objects.create(
            user=user_b,
            geographic_unit=district_kyenjojo,
            priority=1,
        )
        assert ufr_a.geographic_unit == ufr_b.geographic_unit

    def test_archived_geographic_unit_rejected(
        self,
        user_a: User,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Archived unit cannot be configured as a familiar region."""
        district_kyenjojo.status = GeographicUnitStatus.ARCHIVED
        district_kyenjojo.save()

        ufr = UserFamiliarRegion(
            user=user_a,
            geographic_unit=district_kyenjojo,
            priority=1,
        )
        with pytest.raises(ValidationError) as excinfo:
            ufr.clean()
        assert "archived geographic unit" in str(excinfo.value)

    def test_priority_accepts_valid_positive_values(
        self,
        user_a: User,
        country_uganda: GeographicUnit,
        region_western: GeographicUnit,
    ) -> None:
        """Positive integer priorities are valid."""
        ufr_1 = UserFamiliarRegion(
            user=user_a, geographic_unit=country_uganda, priority=1
        )
        ufr_2 = UserFamiliarRegion(
            user=user_a, geographic_unit=region_western, priority=5
        )
        ufr_1.clean()
        ufr_2.clean()
        ufr_1.save()
        ufr_2.save()
        assert ufr_1.priority == 1
        assert ufr_2.priority == 5

    def test_priority_less_than_one_rejected(
        self,
        user_a: User,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Priority < 1 raises ValidationError."""
        ufr = UserFamiliarRegion(
            user=user_a,
            geographic_unit=district_kyenjojo,
            priority=0,
        )
        with pytest.raises(ValidationError) as excinfo:
            ufr.clean()
        assert "greater than or equal to 1" in str(excinfo.value)

    def test_shared_priority_allowed_temporarily_during_reorder(
        self,
        user_a: User,
        country_uganda: GeographicUnit,
        region_western: GeographicUnit,
    ) -> None:
        """Two familiar regions can temporarily share priority during reordering."""
        ufr_1 = UserFamiliarRegion.objects.create(
            user=user_a,
            geographic_unit=country_uganda,
            priority=1,
        )
        ufr_2 = UserFamiliarRegion.objects.create(
            user=user_a,
            geographic_unit=region_western,
            priority=1,
        )
        assert ufr_1.priority == ufr_2.priority == 1

    def test_user_deletion_cascades(
        self,
        user_a: User,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Deleting a user cascades to their UserFamiliarRegion records."""
        user_id = user_a.id
        UserFamiliarRegion.objects.create(
            user=user_a,
            geographic_unit=district_kyenjojo,
            priority=1,
        )
        assert UserFamiliarRegion.objects.filter(user_id=user_id).count() == 1
        user_a.delete()
        assert UserFamiliarRegion.objects.filter(user_id=user_id).count() == 0


# ---------------------------------------------------------------------------
# 5. InstitutionContextRegion Model Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestInstitutionContextRegion:
    """Tests for InstitutionContextRegion configuration."""

    def test_create_valid_institution_context_region(
        self,
        institution_a: Institution,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Create a valid institution context region."""
        icr = InstitutionContextRegion(
            institution=institution_a,
            geographic_unit=district_kyenjojo,
            priority=1,
        )
        icr.clean()
        icr.save()

        assert icr.institution == institution_a
        assert icr.geographic_unit == district_kyenjojo
        assert icr.priority == 1
        assert "Priority 1" in str(icr)

    def test_same_institution_cannot_select_same_unit_twice(
        self,
        institution_a: Institution,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Institution cannot add the same geographic unit more than once."""
        InstitutionContextRegion.objects.create(
            institution=institution_a,
            geographic_unit=district_kyenjojo,
            priority=1,
        )
        with pytest.raises(IntegrityError):
            InstitutionContextRegion.objects.create(
                institution=institution_a,
                geographic_unit=district_kyenjojo,
                priority=2,
            )

    def test_different_institutions_can_select_same_unit(
        self,
        institution_a: Institution,
        institution_b: Institution,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Distinct institutions can configure the same geographic unit."""
        icr_a = InstitutionContextRegion.objects.create(
            institution=institution_a,
            geographic_unit=district_kyenjojo,
            priority=1,
        )
        icr_b = InstitutionContextRegion.objects.create(
            institution=institution_b,
            geographic_unit=district_kyenjojo,
            priority=1,
        )
        assert icr_a.geographic_unit == icr_b.geographic_unit

    def test_archived_geographic_unit_rejected(
        self,
        institution_a: Institution,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Archived unit cannot be configured as an institution context region."""
        district_kyenjojo.status = GeographicUnitStatus.ARCHIVED
        district_kyenjojo.save()

        icr = InstitutionContextRegion(
            institution=institution_a,
            geographic_unit=district_kyenjojo,
            priority=1,
        )
        with pytest.raises(ValidationError) as excinfo:
            icr.clean()
        assert "archived geographic unit" in str(excinfo.value)

    def test_priority_validation(
        self,
        institution_a: Institution,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Priority < 1 raises ValidationError."""
        icr = InstitutionContextRegion(
            institution=institution_a,
            geographic_unit=district_kyenjojo,
            priority=0,
        )
        with pytest.raises(ValidationError) as excinfo:
            icr.clean()
        assert "greater than or equal to 1" in str(excinfo.value)

    def test_institution_deletion_cascades(
        self,
        institution_a: Institution,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Deleting an institution cascades to its context region records."""
        inst_id = institution_a.id
        InstitutionContextRegion.objects.create(
            institution=institution_a,
            geographic_unit=district_kyenjojo,
            priority=1,
        )
        assert (
            InstitutionContextRegion.objects.filter(institution_id=inst_id).count() == 1
        )
        institution_a.delete()
        assert (
            InstitutionContextRegion.objects.filter(institution_id=inst_id).count() == 0
        )


# ---------------------------------------------------------------------------
# 6. Tag Normalization Tests
# ---------------------------------------------------------------------------


class TestTagNormalization:
    """Tests for pedagogical tag normalization helpers."""

    def test_normalize_tags_lowercase_and_trim(self) -> None:
        """Tags are lowercased, trimmed, and deduplicated."""
        raw = ["  Biology  ", "AGRICULTURE", "biology", "  Crop Farming "]
        normalized = normalize_tags(raw)
        assert normalized == ["biology", "agriculture", "crop farming"]

    def test_normalize_tags_empty_and_invalid(self) -> None:
        """Empty strings, whitespace-only strings, and non-strings are omitted."""
        raw = ["", "   ", None, 123, " valid tag "]
        normalized = normalize_tags(raw)
        assert normalized == ["valid tag"]

    def test_normalize_tags_non_list_input(self) -> None:
        """Non-list input returns an empty list."""
        assert normalize_tags(None) == []
        assert normalize_tags("string_not_list") == []
        assert normalize_tags(42) == []
