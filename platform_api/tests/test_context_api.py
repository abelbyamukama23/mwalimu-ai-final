"""API integration tests for Mwalimu context configuration and management endpoints."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from platform_api.apps.context.models import (
    ContextDomain,
    ContextResource,
    ContextScopeType,
    GeographicUnit,
    GeographicUnitStatus,
    GeographicUnitType,
    InstitutionContextRegion,
    UserFamiliarRegion,
)
from platform_api.apps.institutions.models import Institution
from platform_api.apps.memberships.models import (
    Membership,
)
from platform_api.apps.users.models import User


def _results(resp: Any) -> list[dict[str, Any]]:
    """Helper to extract result items from DRF paginated or unpaginated responses."""
    data = resp.json()
    if isinstance(data, dict) and "results" in data:
        return data["results"]  # type: ignore[no-any-return]
    if isinstance(data, list):
        return data
    return []


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
    )


@pytest.fixture
def subcounty_kyarusozi(db: None, district_kyenjojo: GeographicUnit) -> GeographicUnit:
    """Return Kyarusozi Subcounty under Kyenjojo."""
    return GeographicUnit.objects.create(
        name="Kyarusozi Subcounty",
        slug="kyarusozi",
        unit_type=GeographicUnitType.SUBCOUNTY,
        parent=district_kyenjojo,
        country_code="UG",
        status=GeographicUnitStatus.ACTIVE,
    )


@pytest.fixture
def archived_district(db: None, region_western: GeographicUnit) -> GeographicUnit:
    """Return an archived district."""
    return GeographicUnit.objects.create(
        name="Old District",
        slug="old-district",
        unit_type=GeographicUnitType.DISTRICT,
        parent=region_western,
        country_code="UG",
        status=GeographicUnitStatus.ARCHIVED,
    )


@pytest.fixture
def domain_agriculture(db: None) -> ContextDomain:
    """Return Agriculture domain."""
    return ContextDomain.objects.create(
        name="Agriculture & Farming",
        slug="agriculture",
        description="Farming practices and local agronomy.",
    )


@pytest.fixture
def domain_climate(db: None) -> ContextDomain:
    """Return Climate domain."""
    return ContextDomain.objects.create(
        name="Climate & Environment",
        slug="climate",
        description="Rainfall, seasons, and ecology.",
    )


@pytest.fixture
def platform_admin_user(db: None) -> User:
    """Return a platform administrator user."""
    return User.objects.create_superuser(
        email="platform.admin@example.com",
        password="admin-password-123",
    )


@pytest.fixture
def platform_admin_client(platform_admin_user: User) -> APIClient:
    """Return API client authenticated as platform admin."""
    client = APIClient()
    client.force_authenticate(user=platform_admin_user)
    return client


# ---------------------------------------------------------------------------
# 1. Anonymous Access Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAnonymousAccess:
    """Verify all context endpoints require authentication."""

    def test_anonymous_access_rejected(
        self,
        api_client: APIClient,
        institution_a: Institution,
    ) -> None:
        """Unauthenticated requests receive 401 Unauthorized."""
        assert api_client.get("/api/v1/context/geographic-units/").status_code == 401
        assert api_client.get("/api/v1/context/familiar-regions/").status_code == 401
        assert (
            api_client.get(
                f"/api/v1/institutions/{institution_a.id}/context-regions/"
            ).status_code
            == 401
        )
        assert api_client.get("/api/v1/context/resources/").status_code == 401


# ---------------------------------------------------------------------------
# 2. GeographicUnit Discovery Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGeographicUnitDiscovery:
    """Tests for discovering geographic units."""

    def test_list_geographic_units_excludes_archived_by_default(
        self,
        client_a: APIClient,
        country_uganda: GeographicUnit,
        district_kyenjojo: GeographicUnit,
        archived_district: GeographicUnit,
    ) -> None:
        """Active units are listed; archived units are excluded by default."""
        resp = client_a.get("/api/v1/context/geographic-units/")
        assert resp.status_code == 200
        results = _results(resp)
        names = [item["name"] for item in results]
        assert "Uganda" in names
        assert "Kyenjojo District" in names
        assert "Old District" not in names

    def test_list_geographic_units_filter_by_parent(
        self,
        client_a: APIClient,
        country_uganda: GeographicUnit,
        region_western: GeographicUnit,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Filter by parent_id (root vs child)."""
        # Filter root units
        resp_root = client_a.get("/api/v1/context/geographic-units/?parent_id=null")
        assert resp_root.status_code == 200
        root_names = [item["name"] for item in _results(resp_root)]
        assert "Uganda" in root_names
        assert "Western Region" not in root_names

        # Filter children of Western Region
        resp_child = client_a.get(
            f"/api/v1/context/geographic-units/?parent_id={region_western.id}"
        )
        assert resp_child.status_code == 200
        child_names = [item["name"] for item in _results(resp_child)]
        assert "Kyenjojo District" in child_names
        assert "Uganda" not in child_names

    def test_list_geographic_units_search_query(
        self,
        client_a: APIClient,
        district_kyenjojo: GeographicUnit,
        country_uganda: GeographicUnit,
    ) -> None:
        """Case-insensitive search on name or slug."""
        resp = client_a.get("/api/v1/context/geographic-units/?query=kyenjojo")
        assert resp.status_code == 200
        results = _results(resp)
        assert len(results) == 1
        assert results[0]["name"] == "Kyenjojo District"

    def test_retrieve_geographic_unit_detail_with_ancestors(
        self,
        client_a: APIClient,
        subcounty_kyarusozi: GeographicUnit,
        district_kyenjojo: GeographicUnit,
        region_western: GeographicUnit,
        country_uganda: GeographicUnit,
    ) -> None:
        """Retrieving a unit returns its full ancestor hierarchy chain."""
        resp = client_a.get(
            f"/api/v1/context/geographic-units/{subcounty_kyarusozi.id}/"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(subcounty_kyarusozi.id)
        assert data["name"] == "Kyarusozi Subcounty"

        ancestors = data["ancestors"]
        assert len(ancestors) == 3
        # Ancestors ordered root -> parent
        assert ancestors[0]["name"] == "Uganda"
        assert ancestors[0]["unit_type"] == "country"
        assert ancestors[1]["name"] == "Western Region"
        assert ancestors[1]["unit_type"] == "region"
        assert ancestors[2]["name"] == "Kyenjojo District"
        assert ancestors[2]["unit_type"] == "district"


# ---------------------------------------------------------------------------
# 3. User Familiar Regions Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUserFamiliarRegions:
    """Tests for user familiar region configuration."""

    def test_list_and_create_user_familiar_region(
        self,
        client_a: APIClient,
        user_a: User,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """User can add and list familiar regions."""
        resp_post = client_a.post(
            "/api/v1/context/familiar-regions/",
            {"geographic_unit_id": str(district_kyenjojo.id), "priority": 1},
            format="json",
        )
        assert resp_post.status_code == 201
        data = resp_post.json()
        assert data["priority"] == 1
        assert data["geographic_unit"]["name"] == "Kyenjojo District"

        # List verifies it is present
        resp_list = client_a.get("/api/v1/context/familiar-regions/")
        assert resp_list.status_code == 200
        assert len(_results(resp_list)) == 1

    def test_create_duplicate_familiar_region_rejected(
        self,
        client_a: APIClient,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Adding duplicate geographic unit returns 400 ValidationError."""
        client_a.post(
            "/api/v1/context/familiar-regions/",
            {"geographic_unit_id": str(district_kyenjojo.id)},
            format="json",
        )
        resp_dup = client_a.post(
            "/api/v1/context/familiar-regions/",
            {"geographic_unit_id": str(district_kyenjojo.id)},
            format="json",
        )
        assert resp_dup.status_code == 400
        assert "already in your familiar regions" in str(resp_dup.json())

    def test_create_archived_geographic_unit_rejected(
        self,
        client_a: APIClient,
        archived_district: GeographicUnit,
    ) -> None:
        """Configuring an archived unit as a familiar region returns 400."""
        resp = client_a.post(
            "/api/v1/context/familiar-regions/",
            {"geographic_unit_id": str(archived_district.id)},
            format="json",
        )
        assert resp.status_code == 400
        assert "archived geographic unit" in str(resp.json())

    def test_delete_user_familiar_region(
        self,
        client_a: APIClient,
        user_a: User,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """User can delete their own familiar region."""
        ufr = UserFamiliarRegion.objects.create(
            user=user_a,
            geographic_unit=district_kyenjojo,
            priority=1,
        )
        resp = client_a.delete(f"/api/v1/context/familiar-regions/{ufr.id}/")
        assert resp.status_code == 204
        assert not UserFamiliarRegion.objects.filter(id=ufr.id).exists()

    def test_user_cannot_delete_other_users_familiar_region(
        self,
        client_a: APIClient,
        user_b: User,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """User A cannot delete User B's familiar region."""
        ufr_b = UserFamiliarRegion.objects.create(
            user=user_b,
            geographic_unit=district_kyenjojo,
            priority=1,
        )
        resp = client_a.delete(f"/api/v1/context/familiar-regions/{ufr_b.id}/")
        assert resp.status_code == 404
        assert UserFamiliarRegion.objects.filter(id=ufr_b.id).exists()

    def test_atomic_reorder_user_familiar_regions(
        self,
        client_a: APIClient,
        user_a: User,
        country_uganda: GeographicUnit,
        region_western: GeographicUnit,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Atomic reorder endpoint updates priorities to 1..N."""
        ufr_1 = UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=country_uganda, priority=1
        )
        ufr_2 = UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=region_western, priority=2
        )
        ufr_3 = UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=3
        )

        # Reverse order: ufr_3 (1), ufr_2 (2), ufr_1 (3)
        resp = client_a.put(
            "/api/v1/context/familiar-regions/reorder/",
            {"region_ids": [str(ufr_3.id), str(ufr_2.id), str(ufr_1.id)]},
            format="json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert data[0]["id"] == str(ufr_3.id)
        assert data[0]["priority"] == 1
        assert data[1]["id"] == str(ufr_2.id)
        assert data[1]["priority"] == 2
        assert data[2]["id"] == str(ufr_1.id)
        assert data[2]["priority"] == 3

    def test_reorder_with_duplicate_or_foreign_ids_rejected(
        self,
        client_a: APIClient,
        user_a: User,
        user_b: User,
        country_uganda: GeographicUnit,
        region_western: GeographicUnit,
    ) -> None:
        """Reorder with duplicate or foreign user IDs fails and rolls back."""
        ufr_a = UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=country_uganda, priority=1
        )
        ufr_b = UserFamiliarRegion.objects.create(
            user=user_b, geographic_unit=region_western, priority=1
        )

        # Duplicate ID
        resp_dup = client_a.put(
            "/api/v1/context/familiar-regions/reorder/",
            {"region_ids": [str(ufr_a.id), str(ufr_a.id)]},
            format="json",
        )
        assert resp_dup.status_code == 400

        # Foreign ID
        resp_foreign = client_a.put(
            "/api/v1/context/familiar-regions/reorder/",
            {"region_ids": [str(ufr_b.id)]},
            format="json",
        )
        assert resp_foreign.status_code == 400

    def test_reorder_user_familiar_regions_missing_ids_rejected(
        self,
        client_a: APIClient,
        user_a: User,
        country_uganda: GeographicUnit,
        region_western: GeographicUnit,
    ) -> None:
        """Submitting an incomplete subset of IDs is rejected."""
        ufr_1 = UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=country_uganda, priority=1
        )
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=region_western, priority=2
        )
        resp = client_a.put(
            "/api/v1/context/familiar-regions/reorder/",
            {"region_ids": [str(ufr_1.id)]},
            format="json",
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 4. Institution Context Regions Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestInstitutionContextRegions:
    """Tests for institution-scoped context regions."""

    def test_list_institution_context_regions_as_member(
        self,
        client_a: APIClient,
        membership_a: Membership,
        institution_a: Institution,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Active member can list context regions for their institution."""
        InstitutionContextRegion.objects.create(
            institution=institution_a,
            geographic_unit=district_kyenjojo,
            priority=1,
        )
        resp = client_a.get(f"/api/v1/institutions/{institution_a.id}/context-regions/")
        assert resp.status_code == 200
        assert len(_results(resp)) == 1

    def test_list_institution_context_regions_non_member_forbidden(
        self,
        client_b: APIClient,
        institution_a: Institution,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Non-member cannot view another institution's context regions."""
        resp = client_b.get(f"/api/v1/institutions/{institution_a.id}/context-regions/")
        assert resp.status_code == 403

    def test_create_and_delete_institution_context_region_as_admin(
        self,
        admin_client_a: APIClient,
        institution_a: Institution,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Institution admin can create and delete context regions."""
        resp_create = admin_client_a.post(
            f"/api/v1/institutions/{institution_a.id}/context-regions/",
            {"geographic_unit_id": str(district_kyenjojo.id), "priority": 1},
            format="json",
        )
        assert resp_create.status_code == 201
        region_id = resp_create.json()["id"]

        resp_del = admin_client_a.delete(
            f"/api/v1/institutions/{institution_a.id}/context-regions/{region_id}/"
        )
        assert resp_del.status_code == 204

    def test_create_institution_context_region_as_student_forbidden(
        self,
        client_a: APIClient,
        membership_a: Membership,
        institution_a: Institution,
        district_kyenjojo: GeographicUnit,
    ) -> None:
        """Non-admin member cannot create institution context region."""
        # membership_a role is TEACHER (not ADMINISTRATOR)
        resp = client_a.post(
            f"/api/v1/institutions/{institution_a.id}/context-regions/",
            {"geographic_unit_id": str(district_kyenjojo.id)},
            format="json",
        )
        assert resp.status_code == 403

    def test_reorder_institution_context_regions(
        self,
        admin_client_a: APIClient,
        institution_a: Institution,
        country_uganda: GeographicUnit,
        region_western: GeographicUnit,
    ) -> None:
        """Institution admin can reorder context regions."""
        icr_1 = InstitutionContextRegion.objects.create(
            institution=institution_a, geographic_unit=country_uganda, priority=1
        )
        icr_2 = InstitutionContextRegion.objects.create(
            institution=institution_a, geographic_unit=region_western, priority=2
        )

        resp = admin_client_a.put(
            f"/api/v1/institutions/{institution_a.id}/context-regions/reorder/",
            {"region_ids": [str(icr_2.id), str(icr_1.id)]},
            format="json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["id"] == str(icr_2.id)
        assert data[0]["priority"] == 1

    def test_reorder_institution_context_regions_as_student_forbidden(
        self,
        client_a: APIClient,
        membership_a: Membership,
        institution_a: Institution,
        country_uganda: GeographicUnit,
    ) -> None:
        """Non-admin member cannot reorder institution context regions."""
        icr = InstitutionContextRegion.objects.create(
            institution=institution_a, geographic_unit=country_uganda, priority=1
        )
        resp = client_a.put(
            f"/api/v1/institutions/{institution_a.id}/context-regions/reorder/",
            {"region_ids": [str(icr.id)]},
            format="json",
        )
        assert resp.status_code == 403

    def test_reorder_institution_context_regions_duplicate_ids_rejected(
        self,
        admin_client_a: APIClient,
        institution_a: Institution,
        country_uganda: GeographicUnit,
    ) -> None:
        """Duplicate IDs in reorder request are rejected."""
        icr = InstitutionContextRegion.objects.create(
            institution=institution_a, geographic_unit=country_uganda, priority=1
        )
        resp = admin_client_a.put(
            f"/api/v1/institutions/{institution_a.id}/context-regions/reorder/",
            {"region_ids": [str(icr.id), str(icr.id)]},
            format="json",
        )
        assert resp.status_code == 400

    def test_reorder_institution_context_regions_cross_institution_rejected(
        self,
        admin_client_a: APIClient,
        institution_a: Institution,
        institution_b: Institution,
        country_uganda: GeographicUnit,
        region_western: GeographicUnit,
    ) -> None:
        """Reordering with another institution's region ID is rejected."""
        InstitutionContextRegion.objects.create(
            institution=institution_a, geographic_unit=country_uganda, priority=1
        )
        icr_b = InstitutionContextRegion.objects.create(
            institution=institution_b, geographic_unit=region_western, priority=1
        )
        resp = admin_client_a.put(
            f"/api/v1/institutions/{institution_a.id}/context-regions/reorder/",
            {"region_ids": [str(icr_b.id)]},
            format="json",
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 5. ContextResource Management & Scoping Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestContextResourceManagement:
    """Tests for managing ContextResource items with platform and tenant boundaries."""

    def test_list_context_resources_tenant_visibility(
        self,
        client_a: APIClient,
        membership_a: Membership,
        institution_a: Institution,
        institution_b: Institution,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """User A sees PLATFORM and Inst A resources, not Inst B."""
        # 1. Platform resource
        res_platform = ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Uganda Tea Industry",
            content="Tea production across Uganda.",
            scope_type=ContextScopeType.PLATFORM,
        )
        # 2. Institution A resource
        res_inst_a = ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="School Garden A",
            content="Institution A garden project.",
            scope_type=ContextScopeType.INSTITUTION,
            institution=institution_a,
        )
        # 3. Institution B resource
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="School Garden B",
            content="Institution B garden project.",
            scope_type=ContextScopeType.INSTITUTION,
            institution=institution_b,
        )

        resp = client_a.get("/api/v1/context/resources/")
        assert resp.status_code == 200
        ids = [item["id"] for item in _results(resp)]
        assert str(res_platform.id) in ids
        assert str(res_inst_a.id) in ids
        assert len(ids) == 2

    def test_create_platform_context_resource_as_platform_admin(
        self,
        platform_admin_client: APIClient,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Platform admin can create platform-scoped context resources."""
        payload = {
            "geographic_unit_id": str(district_kyenjojo.id),
            "context_domain_id": str(domain_agriculture.id),
            "title": "Kyenjojo Tea Estates",
            "content": "Large tea plantations are common in Kyenjojo.",
            "scope_type": "platform",
            "applicable_subjects": ["Biology", "Agriculture"],
            "applicable_topics": ["Photosynthesis"],
            "pedagogical_purposes": ["example", "explanation"],
        }
        resp = platform_admin_client.post(
            "/api/v1/context/resources/", payload, format="json"
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Kyenjojo Tea Estates"
        assert data["applicable_subjects"] == ["biology", "agriculture"]
        assert data["applicable_topics"] == ["photosynthesis"]
        assert data["pedagogical_purposes"] == ["example", "explanation"]

    def test_create_platform_context_resource_as_institution_admin_forbidden(
        self,
        admin_client_a: APIClient,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Institution admin cannot create platform-scoped resources."""
        payload = {
            "geographic_unit_id": str(district_kyenjojo.id),
            "context_domain_id": str(domain_agriculture.id),
            "title": "Platform Resource Attempt",
            "content": "Sample content.",
            "scope_type": "platform",
        }
        resp = admin_client_a.post("/api/v1/context/resources/", payload, format="json")
        assert resp.status_code == 403

    def test_create_institution_context_resource_as_institution_admin(
        self,
        admin_client_a: APIClient,
        institution_a: Institution,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Institution admin can create institution-scoped context resources."""
        payload = {
            "geographic_unit_id": str(district_kyenjojo.id),
            "context_domain_id": str(domain_agriculture.id),
            "title": "Institution Farm Guide",
            "content": "Experimental crop guide for Institution A.",
            "scope_type": "institution",
            "institution_id": str(institution_a.id),
            "applicable_subjects": ["Agriculture"],
            "pedagogical_purposes": ["activity"],
        }
        resp = admin_client_a.post("/api/v1/context/resources/", payload, format="json")
        assert resp.status_code == 201
        assert resp.json()["institution_id"] == str(institution_a.id)

    def test_create_institution_context_resource_for_other_institution_forbidden(
        self,
        admin_client_a: APIClient,
        institution_b: Institution,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Institution A admin cannot create resources for Institution B."""
        payload = {
            "geographic_unit_id": str(district_kyenjojo.id),
            "context_domain_id": str(domain_agriculture.id),
            "title": "Cross Tenant Attempt",
            "content": "Sample content.",
            "scope_type": "institution",
            "institution_id": str(institution_b.id),
        }
        resp = admin_client_a.post("/api/v1/context/resources/", payload, format="json")
        assert resp.status_code == 403

    def test_context_resource_filtering(
        self,
        client_a: APIClient,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
        domain_climate: ContextDomain,
    ) -> None:
        """Filter context resources by pedagogical tags, domains, and keywords."""
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Coffee Harvesting",
            content="Harvesting arabica coffee.",
            scope_type=ContextScopeType.PLATFORM,
            applicable_subjects=["agriculture", "economics"],
            applicable_topics=["crop production"],
            pedagogical_purposes=["example"],
        )
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_climate,
            title="Rainfall in Rwenzori",
            content="Bimodal rainfall pattern.",
            scope_type=ContextScopeType.PLATFORM,
            applicable_subjects=["geography"],
            applicable_topics=["climate"],
            pedagogical_purposes=["explanation"],
        )

        # Filter by subject
        resp_subj = client_a.get(
            "/api/v1/context/resources/?applicable_subject=Agriculture"
        )
        assert resp_subj.status_code == 200
        results_subj = _results(resp_subj)
        assert len(results_subj) == 1
        assert results_subj[0]["title"] == "Coffee Harvesting"

        # Filter by pedagogical purpose
        resp_purp = client_a.get(
            "/api/v1/context/resources/?pedagogical_purpose=explanation"
        )
        assert resp_purp.status_code == 200
        results_purp = _results(resp_purp)
        assert len(results_purp) == 1
        assert results_purp[0]["title"] == "Rainfall in Rwenzori"

    def test_retrieve_context_resource_detail(
        self,
        client_a: APIClient,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Retrieve detail of a platform context resource."""
        res = ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Uganda Farming Detail",
            content="Detailed farming snippet.",
            scope_type=ContextScopeType.PLATFORM,
        )
        resp = client_a.get(f"/api/v1/context/resources/{res.id}/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(res.id)
        assert data["title"] == "Uganda Farming Detail"
        assert data["geographic_unit"]["name"] == "Kyenjojo District"
        assert data["context_domain"]["name"] == "Agriculture & Farming"

    def test_retrieve_other_institution_resource_returns_404(
        self,
        client_a: APIClient,
        institution_b: Institution,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """User A attempting to retrieve Institution B resource receives 404."""
        res_b = ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Institution B Private Farm",
            content="Private snippet.",
            scope_type=ContextScopeType.INSTITUTION,
            institution=institution_b,
        )
        resp = client_a.get(f"/api/v1/context/resources/{res_b.id}/")
        assert resp.status_code == 404

    def test_update_institution_context_resource_as_admin(
        self,
        admin_client_a: APIClient,
        institution_a: Institution,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Institution admin can update their institution's resource."""
        res = ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Initial Title",
            content="Initial content.",
            scope_type=ContextScopeType.INSTITUTION,
            institution=institution_a,
        )
        resp = admin_client_a.patch(
            f"/api/v1/context/resources/{res.id}/",
            {"title": "Updated Title"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"

    def test_update_institution_context_resource_as_student_forbidden(
        self,
        client_a: APIClient,
        membership_a: Membership,
        institution_a: Institution,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Student cannot update institution resource."""
        res = ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Initial Title",
            content="Initial content.",
            scope_type=ContextScopeType.INSTITUTION,
            institution=institution_a,
        )
        resp = client_a.patch(
            f"/api/v1/context/resources/{res.id}/",
            {"title": "Student Update Attempt"},
            format="json",
        )
        assert resp.status_code == 403

    def test_delete_context_resource_as_authorized_admin(
        self,
        admin_client_a: APIClient,
        institution_a: Institution,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Institution admin can delete their institution's resource."""
        res = ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="To Be Deleted",
            content="Content.",
            scope_type=ContextScopeType.INSTITUTION,
            institution=institution_a,
        )
        resp = admin_client_a.delete(f"/api/v1/context/resources/{res.id}/")
        assert resp.status_code == 204
        assert not ContextResource.objects.filter(id=res.id).exists()

    def test_create_context_resource_content_too_long_rejected(
        self,
        platform_admin_client: APIClient,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Content exceeding 5000 characters is rejected with 400."""
        payload = {
            "geographic_unit_id": str(district_kyenjojo.id),
            "context_domain_id": str(domain_agriculture.id),
            "title": "Long Content Resource",
            "content": "A" * 5001,
            "scope_type": "platform",
        }
        resp = platform_admin_client.post(
            "/api/v1/context/resources/", payload, format="json"
        )
        assert resp.status_code == 400
        assert "5000" in str(resp.json())

    def test_create_context_resource_invalid_pedagogical_purpose_rejected(
        self,
        platform_admin_client: APIClient,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Invalid pedagogical purpose is rejected with 400."""
        payload = {
            "geographic_unit_id": str(district_kyenjojo.id),
            "context_domain_id": str(domain_agriculture.id),
            "title": "Invalid Purpose Resource",
            "content": "Content.",
            "scope_type": "platform",
            "pedagogical_purposes": ["invalid_purpose"],
        }
        resp = platform_admin_client.post(
            "/api/v1/context/resources/", payload, format="json"
        )
        assert resp.status_code == 400
        assert "Invalid pedagogical purpose" in str(resp.json())

    def test_create_platform_resource_with_institution_rejected(
        self,
        platform_admin_client: APIClient,
        institution_a: Institution,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Platform resource specifying an institution is rejected with 400."""
        payload = {
            "geographic_unit_id": str(district_kyenjojo.id),
            "context_domain_id": str(domain_agriculture.id),
            "title": "Invalid Platform Resource",
            "content": "Content.",
            "scope_type": "platform",
            "institution_id": str(institution_a.id),
        }
        resp = platform_admin_client.post(
            "/api/v1/context/resources/", payload, format="json"
        )
        assert resp.status_code == 400
        assert "Platform resources must not specify an institution" in str(resp.json())

    def test_create_institution_resource_with_null_institution_rejected(
        self,
        platform_admin_client: APIClient,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Institution resource with null institution is rejected with 400."""
        payload = {
            "geographic_unit_id": str(district_kyenjojo.id),
            "context_domain_id": str(domain_agriculture.id),
            "title": "Invalid Institution Resource",
            "content": "Content.",
            "scope_type": "institution",
            "institution_id": None,
        }
        resp = platform_admin_client.post(
            "/api/v1/context/resources/", payload, format="json"
        )
        assert resp.status_code == 400
        assert "Institution resources must specify an institution" in str(resp.json())
