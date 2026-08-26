"""Integration tests for ContextResolver integration into run orchestration."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from platform_api.apps.agents.client import AgentServiceClient
from platform_api.apps.agents.models import (
    AgentRunRecord,
    AgentRunStatus,
    AgentSession,
)
from platform_api.apps.agents.orchestration import AgentRunOrchestrationService
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
    MembershipRole,
    MembershipStatus,
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
def district_kyenjojo(db: None, country_uganda: GeographicUnit) -> GeographicUnit:
    """Return Kyenjojo District."""
    return GeographicUnit.objects.create(
        name="Kyenjojo District",
        slug="kyenjojo",
        unit_type=GeographicUnitType.DISTRICT,
        parent=country_uganda,
        country_code="UG",
        status=GeographicUnitStatus.ACTIVE,
        metadata={"aliases": ["Kyenjojo"]},
    )


@pytest.fixture
def district_kampala(db: None, country_uganda: GeographicUnit) -> GeographicUnit:
    """Return Kampala District."""
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
def domain_agriculture(db: None) -> ContextDomain:
    """Return Agriculture context domain."""
    return ContextDomain.objects.create(
        name="Agriculture & Farming",
        slug="agriculture",
        description="Farming practices and crops.",
    )


@pytest.fixture
def user_a(db: None) -> User:
    """Return User A."""
    return User.objects.create_user(
        email="learner_a@example.com",
        password="ValidPassword123!",
    )


@pytest.fixture
def institution_a(db: None) -> Institution:
    """Return Institution A."""
    return Institution.objects.create(
        name="Institution A",
        slug="institution-a",
    )


@pytest.fixture
def institution_b(db: None) -> Institution:
    """Return Institution B."""
    return Institution.objects.create(
        name="Institution B",
        slug="institution-b",
    )


@pytest.fixture
def membership_a(db: None, user_a: User, institution_a: Institution) -> Membership:
    """Return active student membership in Institution A."""
    return Membership.objects.create(
        user=user_a,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )


@pytest.fixture
def session_a(db: None, user_a: User, institution_a: Institution) -> AgentSession:
    """Return AgentSession for User A in Institution A."""
    return AgentSession.objects.create(
        user=user_a,
        institution=institution_a,
        title="Learning Session",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestContextOrchestrationIntegration:
    """Integration tests verifying ContextResolver in AgentRunOrchestrationService."""

    def test_relevant_pedagogical_context_dispatched_in_payload(
        self,
        session_a: AgentSession,
        user_a: User,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Relevant prompt dispatches resolved context items in HTTP payload."""
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Kyenjojo Tea Production",
            content="Tea plantations thrive on volcanic soils.",
            scope_type=ContextScopeType.PLATFORM,
            applicable_subjects=["agriculture"],
            applicable_topics=["tea farming"],
            pedagogical_purposes=["example"],
        )

        captured_body: dict[str, object] = {}

        def mock_handler(request: httpx.Request) -> httpx.Response:
            captured_body.update(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                status_code=202,
                json={
                    "id": str(uuid.uuid4()),
                    "session_id": str(session_a.pk),
                    "status": "queued",
                    "prompt": request.url.path,
                    "created_at": "2026-08-24T10:00:00Z",
                },
            )

        transport = httpx.MockTransport(mock_handler)
        client = AgentServiceClient(
            base_url="http://agent-service.test",
            client=httpx.Client(transport=transport),
        )
        service = AgentRunOrchestrationService(client=client)

        run = service.dispatch_session_run(
            session=session_a,
            user=user_a,
            prompt="Explain tea farming in my area using a local example.",
        )

        assert isinstance(run, AgentRunRecord)
        assert run.status == AgentRunStatus.QUEUED
        assert "context" in captured_body
        context_data = captured_body["context"]
        assert isinstance(context_data, dict)
        assert context_data["context_considered"] is True
        assert len(context_data["items"]) == 1
        assert context_data["items"][0]["title"] == "Kyenjojo Tea Production"
        assert "Kyenjojo" in context_data["items"][0]["geographic_unit_name"]

    def test_irrelevant_prompt_dispatches_empty_context(
        self,
        session_a: AgentSession,
        user_a: User,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Purely abstract prompt dispatches context_considered=False."""
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Kyenjojo Tea Production",
            content="Tea plantations thrive on volcanic soils.",
            scope_type=ContextScopeType.PLATFORM,
        )

        captured_body: dict[str, object] = {}

        def mock_handler(request: httpx.Request) -> httpx.Response:
            captured_body.update(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                status_code=202,
                json={
                    "id": str(uuid.uuid4()),
                    "session_id": str(session_a.pk),
                    "status": "queued",
                    "prompt": "prompt",
                    "created_at": "2026-08-24T10:00:00Z",
                },
            )

        transport = httpx.MockTransport(mock_handler)
        client = AgentServiceClient(
            base_url="http://agent-service.test",
            client=httpx.Client(transport=transport),
        )
        service = AgentRunOrchestrationService(client=client)

        service.dispatch_session_run(
            session=session_a,
            user=user_a,
            prompt="What is the chemical formula of water?",
        )

        assert "context" in captured_body
        context_data = captured_body["context"]
        assert isinstance(context_data, dict)
        assert context_data["context_considered"] is False
        assert len(context_data["items"]) == 0

    def test_explicit_geographic_intent_overrides_familiar_region_in_dispatch(
        self,
        session_a: AgentSession,
        user_a: User,
        district_kyenjojo: GeographicUnit,
        district_kampala: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Prompt explicitly mentioning Kampala targets Kampala over Kyenjojo."""
        # User familiar region is Kyenjojo
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Kyenjojo Tea Production",
            content="Kyenjojo tea.",
            scope_type=ContextScopeType.PLATFORM,
        )
        ContextResource.objects.create(
            geographic_unit=district_kampala,
            context_domain=domain_agriculture,
            title="Kampala Urban Gardening",
            content="Kampala hydroponics.",
            scope_type=ContextScopeType.PLATFORM,
        )

        captured_body: dict[str, object] = {}

        def mock_handler(request: httpx.Request) -> httpx.Response:
            captured_body.update(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                status_code=202,
                json={
                    "id": str(uuid.uuid4()),
                    "session_id": str(session_a.pk),
                    "status": "queued",
                    "prompt": "prompt",
                    "created_at": "2026-08-24T10:00:00Z",
                },
            )

        transport = httpx.MockTransport(mock_handler)
        client = AgentServiceClient(
            base_url="http://agent-service.test",
            client=httpx.Client(transport=transport),
        )
        service = AgentRunOrchestrationService(client=client)

        service.dispatch_session_run(
            session=session_a,
            user=user_a,
            prompt="Explain agriculture in Kampala.",
        )

        context_data = captured_body["context"]
        assert isinstance(context_data, dict)
        assert context_data["explicit_geographic_intent"] == "Kampala District"
        assert len(context_data["items"]) == 1
        assert context_data["items"][0]["title"] == "Kampala Urban Gardening"

    def test_institution_isolation_preserved_during_orchestration(
        self,
        session_a: AgentSession,
        user_a: User,
        membership_a: Membership,
        institution_a: Institution,
        institution_b: Institution,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Dispatched payload never contains Institution B private resources."""
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )
        # Institution A resource
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="School A Agro Farm",
            content="Private school farm.",
            scope_type=ContextScopeType.INSTITUTION,
            institution=institution_a,
        )
        # Institution B resource
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="School B Secret Project",
            content="Private school B.",
            scope_type=ContextScopeType.INSTITUTION,
            institution=institution_b,
        )

        captured_body: dict[str, object] = {}

        def mock_handler(request: httpx.Request) -> httpx.Response:
            captured_body.update(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                status_code=202,
                json={
                    "id": str(uuid.uuid4()),
                    "session_id": str(session_a.pk),
                    "status": "queued",
                    "prompt": "prompt",
                    "created_at": "2026-08-24T10:00:00Z",
                },
            )

        transport = httpx.MockTransport(mock_handler)
        client = AgentServiceClient(
            base_url="http://agent-service.test",
            client=httpx.Client(transport=transport),
        )
        service = AgentRunOrchestrationService(client=client)

        service.dispatch_session_run(
            session=session_a,
            user=user_a,
            prompt="Explain farming practices in my area.",
        )

        context_data = captured_body["context"]
        assert isinstance(context_data, dict)
        titles = [item["title"] for item in context_data["items"]]
        assert "School A Agro Farm" in titles
        assert "School B Secret Project" not in titles

    def test_institution_fallback_when_user_has_no_familiar_regions(
        self,
        session_a: AgentSession,
        user_a: User,
        membership_a: Membership,
        institution_a: Institution,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """User with no familiar regions falls back to institution focus region."""
        # Institution A has Kyenjojo focus
        InstitutionContextRegion.objects.create(
            institution=institution_a,
            geographic_unit=district_kyenjojo,
            priority=1,
        )
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Kyenjojo Tea Production",
            content="Content.",
            scope_type=ContextScopeType.PLATFORM,
        )

        captured_body: dict[str, object] = {}

        def mock_handler(request: httpx.Request) -> httpx.Response:
            captured_body.update(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                status_code=202,
                json={
                    "id": str(uuid.uuid4()),
                    "session_id": str(session_a.pk),
                    "status": "queued",
                    "prompt": "prompt",
                    "created_at": "2026-08-24T10:00:00Z",
                },
            )

        transport = httpx.MockTransport(mock_handler)
        client = AgentServiceClient(
            base_url="http://agent-service.test",
            client=httpx.Client(transport=transport),
        )
        service = AgentRunOrchestrationService(client=client)

        service.dispatch_session_run(
            session=session_a,
            user=user_a,
            prompt="Explain agriculture in our region.",
        )

        context_data = captured_body["context"]
        assert isinstance(context_data, dict)
        assert context_data["institution_regions_considered"] is True
        assert len(context_data["items"]) == 1
        assert context_data["items"][0]["title"] == "Kyenjojo Tea Production"

    def test_context_budget_limit_enforced_in_orchestration(
        self,
        session_a: AgentSession,
        user_a: User,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Custom context budget limit in extra_metadata is enforced."""
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )
        for i in range(6):
            ContextResource.objects.create(
                geographic_unit=district_kyenjojo,
                context_domain=domain_agriculture,
                title=f"Kyenjojo Item {i}",
                content=f"Content {i}",
                scope_type=ContextScopeType.PLATFORM,
            )

        captured_body: dict[str, object] = {}

        def mock_handler(request: httpx.Request) -> httpx.Response:
            captured_body.update(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                status_code=202,
                json={
                    "id": str(uuid.uuid4()),
                    "session_id": str(session_a.pk),
                    "status": "queued",
                    "prompt": "prompt",
                    "created_at": "2026-08-24T10:00:00Z",
                },
            )

        transport = httpx.MockTransport(mock_handler)
        client = AgentServiceClient(
            base_url="http://agent-service.test",
            client=httpx.Client(transport=transport),
        )
        service = AgentRunOrchestrationService(client=client)

        service.dispatch_session_run(
            session=session_a,
            user=user_a,
            prompt="Explain local farming in my area.",
            extra_metadata={"context_budget": 2},
        )

        context_data = captured_body["context"]
        assert isinstance(context_data, dict)
        assert len(context_data["items"]) == 2
        assert context_data["budget_limit"] == 2

    def test_multiple_familiar_regions_priority_in_orchestration(
        self,
        session_a: AgentSession,
        user_a: User,
        district_kyenjojo: GeographicUnit,
        district_kampala: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Priority 1 familiar region is queried before Priority 2 in orchestration."""
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kampala, priority=2
        )
        for i in range(3):
            ContextResource.objects.create(
                geographic_unit=district_kyenjojo,
                context_domain=domain_agriculture,
                title=f"Kyenjojo Item {i}",
                content=f"Content {i}",
                scope_type=ContextScopeType.PLATFORM,
            )
            ContextResource.objects.create(
                geographic_unit=district_kampala,
                context_domain=domain_agriculture,
                title=f"Kampala Item {i}",
                content=f"Content {i}",
                scope_type=ContextScopeType.PLATFORM,
            )

        captured_body: dict[str, object] = {}

        def mock_handler(request: httpx.Request) -> httpx.Response:
            captured_body.update(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                status_code=202,
                json={
                    "id": str(uuid.uuid4()),
                    "session_id": str(session_a.pk),
                    "status": "queued",
                    "prompt": "prompt",
                    "created_at": "2026-08-24T10:00:00Z",
                },
            )

        transport = httpx.MockTransport(mock_handler)
        client = AgentServiceClient(
            base_url="http://agent-service.test",
            client=httpx.Client(transport=transport),
        )
        service = AgentRunOrchestrationService(client=client)

        service.dispatch_session_run(
            session=session_a,
            user=user_a,
            prompt="Explain local farming in my area.",
            extra_metadata={"context_budget": 2},
        )

        context_data = captured_body["context"]
        assert isinstance(context_data, dict)
        assert len(context_data["items"]) == 2
        for item in context_data["items"]:
            assert "Kyenjojo" in item["geographic_unit_name"]

    def test_subject_topic_metadata_filtering_in_orchestration(
        self,
        session_a: AgentSession,
        user_a: User,
        district_kyenjojo: GeographicUnit,
        domain_agriculture: ContextDomain,
    ) -> None:
        """Orchestration respects subjects and topics passed in extra_metadata."""
        UserFamiliarRegion.objects.create(
            user=user_a, geographic_unit=district_kyenjojo, priority=1
        )
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="Relevant Tea Photosynthesis",
            content="Biology snippet on tea.",
            scope_type=ContextScopeType.PLATFORM,
            applicable_subjects=["biology"],
            applicable_topics=["photosynthesis"],
        )
        ContextResource.objects.create(
            geographic_unit=district_kyenjojo,
            context_domain=domain_agriculture,
            title="General Livestock Cattle",
            content="Livestock snippet.",
            scope_type=ContextScopeType.PLATFORM,
            applicable_subjects=["agriculture"],
            applicable_topics=["pastoralism"],
        )

        captured_body: dict[str, object] = {}

        def mock_handler(request: httpx.Request) -> httpx.Response:
            captured_body.update(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                status_code=202,
                json={
                    "id": str(uuid.uuid4()),
                    "session_id": str(session_a.pk),
                    "status": "queued",
                    "prompt": "prompt",
                    "created_at": "2026-08-24T10:00:00Z",
                },
            )

        transport = httpx.MockTransport(mock_handler)
        client = AgentServiceClient(
            base_url="http://agent-service.test",
            client=httpx.Client(transport=transport),
        )
        service = AgentRunOrchestrationService(client=client)

        service.dispatch_session_run(
            session=session_a,
            user=user_a,
            prompt="Explain local farming in my area.",
            extra_metadata={
                "subjects": ["biology"],
                "topics": ["photosynthesis"],
                "context_budget": 1,
            },
        )

        context_data = captured_body["context"]
        assert isinstance(context_data, dict)
        assert len(context_data["items"]) == 1
        assert context_data["items"][0]["title"] == "Relevant Tea Photosynthesis"
