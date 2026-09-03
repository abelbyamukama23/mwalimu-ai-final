"""Tests for Stage 7: Resource Disambiguation & Query Intent Guidance."""

from __future__ import annotations

import uuid
import pytest
from rest_framework.test import APIClient

from platform_api.apps.knowledge.authentication import mint_delegated_token
from platform_api.apps.knowledge.dto import SearchRequestDTO
from platform_api.apps.knowledge.policies import EffectiveRetrievalScope
from platform_api.apps.knowledge.query_intent import (
    QueryIntent,
    classify_query_intent,
    detect_query_intent,
    compute_intent_bonus,
)
from platform_api.apps.knowledge.resource_search import (
    find_candidate_resources,
    rank_candidate_resources,
)
from platform_api.apps.knowledge.use_cases import SearchKnowledgeUseCase
from platform_api.apps.libraries.models import Library, LibraryAccessPolicy
from platform_api.apps.memberships.models import Membership
from platform_api.apps.processing.embedding import get_embedding_provider
from platform_api.apps.processing.indexing import activate_run, write_chunks_and_embeddings
from platform_api.apps.processing.models import (
    BookIndexEntry,
    ChunkEmbedding,
    DocumentChunk,
    DocumentStructureNode,
    ProcessingRun,
    ProcessingStatus,
)
from platform_api.apps.resources.models import Resource, ResourceStatus, ResourceType
from platform_api.apps.users.models import User


# ==============================================================================
# 1. INTENT RECOGNITION TESTS (SECTION 21, TESTS 8-15)
# ==============================================================================

def test_query_intent_definitional_detection() -> None:
    """Detect definitional intent across varied common phrasing."""
    res1 = detect_query_intent("What is activation energy?")
    assert res1.intent == QueryIntent.DEFINITIONAL
    assert res1.confidence >= 0.85

    res2 = detect_query_intent("Define chemical equilibrium")
    assert res2.intent == QueryIntent.DEFINITIONAL

    res3 = detect_query_intent("Definition of catalyst")
    assert res3.intent == QueryIntent.DEFINITIONAL

    res4 = detect_query_intent("What are valence electrons?")
    assert res4.intent == QueryIntent.DEFINITIONAL

    res5 = detect_query_intent("What is meant by reaction quotient?")
    assert res5.intent == QueryIntent.DEFINITIONAL


def test_query_intent_procedural_detection() -> None:
    """Detect procedural intent."""
    res1 = detect_query_intent("How do I calculate concentration?")
    assert res1.intent == QueryIntent.PROCEDURAL
    assert res1.confidence >= 0.85

    res2 = detect_query_intent("How to calculate acceleration?")
    assert res2.intent == QueryIntent.PROCEDURAL

    res3 = detect_query_intent("Steps for determining pH")
    assert res3.intent == QueryIntent.PROCEDURAL

    res4 = detect_query_intent("Procedure for calculating molarity")
    assert res4.intent == QueryIntent.PROCEDURAL


def test_query_intent_quantitative_detection() -> None:
    """Detect quantitative calculation requests."""
    res1 = detect_query_intent("Calculate the rate constant.")
    assert res1.intent == QueryIntent.QUANTITATIVE

    res2 = detect_query_intent("Find the value of Kc.")
    assert res2.intent == QueryIntent.QUANTITATIVE

    res3 = detect_query_intent("What is the acceleration if mass is 5kg and force is 20N?")
    assert res3.intent == QueryIntent.QUANTITATIVE


def test_query_intent_overview_detection() -> None:
    """Detect overview/summary requests."""
    res1 = detect_query_intent("Explain photosynthesis.")
    assert res1.intent == QueryIntent.OVERVIEW
    assert res1.confidence >= 0.75

    res2 = detect_query_intent("Give an overview of cellular respiration.")
    assert res2.intent == QueryIntent.OVERVIEW

    res3 = detect_query_intent("Summarize chemical equilibrium.")
    assert res3.intent == QueryIntent.OVERVIEW


def test_query_intent_comparative_detection() -> None:
    """Detect comparative questions between entities."""
    res1 = detect_query_intent("Compare homogeneous and heterogeneous catalysts.")
    assert res1.intent == QueryIntent.COMPARATIVE
    assert res1.confidence >= 0.90

    res2 = detect_query_intent("What is the difference between ionic and covalent bonding?")
    assert res2.intent == QueryIntent.COMPARATIVE

    res3 = detect_query_intent("How are mitosis and meiosis different?")
    assert res3.intent == QueryIntent.COMPARATIVE

    res4 = detect_query_intent("Contrast endothermic and exothermic reactions.")
    assert res4.intent == QueryIntent.COMPARATIVE


def test_query_intent_causal_detection() -> None:
    """Detect causal/mechanistic questions."""
    res1 = detect_query_intent("Why does temperature increase reaction rate?")
    assert res1.intent == QueryIntent.CAUSAL
    assert res1.confidence >= 0.90

    res2 = detect_query_intent("Why does increasing pressure affect equilibrium?")
    assert res2.intent == QueryIntent.CAUSAL

    res3 = detect_query_intent("How does a catalyst make a reaction faster?")
    assert res3.intent == QueryIntent.CAUSAL

    res4 = detect_query_intent("What causes ocean currents?")
    assert res4.intent == QueryIntent.CAUSAL


def test_query_intent_conceptual_fallback() -> None:
    """Fall back to conceptual when explanatory question has no specific cue."""
    res = detect_query_intent("Describe the process of cellular respiration.")
    assert res.intent == QueryIntent.CONCEPTUAL

    res2 = detect_query_intent("activation energy catalyst")
    assert res2.intent is None
    assert classify_query_intent("activation energy catalyst") == QueryIntent.CONCEPTUAL


def test_query_intent_ambiguous_multi_intent() -> None:
    """Preserve multiple signals while selecting highest precedence primary intent."""
    res = detect_query_intent("How do I calculate the numerical value of Kc?")
    # Matches both PROCEDURAL and QUANTITATIVE
    assert QueryIntent.PROCEDURAL in res.intents
    assert QueryIntent.QUANTITATIVE in res.intents
    # Precedence: QUANTITATIVE > PROCEDURAL
    assert res.intent == QueryIntent.QUANTITATIVE


# ==============================================================================
# 2. RESOURCE DISAMBIGUATION TESTS (SECTION 21, TESTS 1-7 & SECTION 22)
# ==============================================================================

@pytest.mark.django_db
def test_resource_exact_title_match(db, library_a: Library, user_a: User) -> None:
    """Exact phrase in resource title receives highest score."""
    res_chem = Resource.objects.create(
        library=library_a,
        name="General Chemistry 12",
        resource_type=ResourceType.PDF,
        original_filename="chem12.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem_title.pdf",
        checksum="hash-chem-title",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    ProcessingRun.objects.create(
        resource=res_chem,
        library=library_a,
        source_checksum=res_chem.checksum,
        pipeline_version="1",
        extractor_version="1",
        chunker_version="1",
        embedding_model="fake-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    res_phys = Resource.objects.create(
        library=library_a,
        name="Physics 101",
        resource_type=ResourceType.PDF,
        original_filename="phys101.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/phys_title.pdf",
        checksum="hash-phys-title",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    ProcessingRun.objects.create(
        resource=res_phys,
        library=library_a,
        source_checksum=res_phys.checksum,
        pipeline_version="1",
        extractor_version="1",
        chunker_version="1",
        embedding_model="fake-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
        is_active=True,
    )

    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    ranked = rank_candidate_resources("general chemistry", scope)
    assert len(ranked) == 2
    assert ranked[0].resource_id == res_chem.id
    assert ranked[0].score >= 10.0


@pytest.mark.django_db
def test_resource_no_match_fallback(db, library_a: Library, user_a: User) -> None:
    """If no resource receives meaningful evidence, fallback keeps all resources without restriction."""
    res_chem = Resource.objects.create(
        library=library_a,
        name="General Chemistry 12",
        resource_type=ResourceType.PDF,
        original_filename="chem12.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem_nomatch.pdf",
        checksum="hash-chem-nomatch",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    ProcessingRun.objects.create(
        resource=res_chem,
        library=library_a,
        source_checksum=res_chem.checksum,
        pipeline_version="1",
        extractor_version="1",
        chunker_version="1",
        embedding_model="fake-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    res_phys = Resource.objects.create(
        library=library_a,
        name="Physics 101",
        resource_type=ResourceType.PDF,
        original_filename="phys101.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/phys_nomatch.pdf",
        checksum="hash-phys-nomatch",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    ProcessingRun.objects.create(
        resource=res_phys,
        library=library_a,
        source_checksum=res_phys.checksum,
        pipeline_version="1",
        extractor_version="1",
        chunker_version="1",
        embedding_model="fake-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
        is_active=True,
    )

    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    prior = find_candidate_resources("quantum entanglement spacetime", scope)
    # Both resources retained, scope not restricted
    assert len(prior.prioritized_resource_ids) == 2
    assert prior.is_scope_restricted is False


@pytest.mark.django_db
def test_multi_book_adversarial_three_way_reciprocal(
    db,
    library_a: Library,
    user_a: User,
    membership_a: Membership,
    library_student_policy_a: LibraryAccessPolicy,
) -> None:
    """Adversarial Test 22: Chemistry vs Physics vs Biology across 3 distinct queries."""
    provider = get_embedding_provider()

    # Resource A: General Chemistry
    res_chem = Resource.objects.create(
        library=library_a,
        name="General Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="chem.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem_adv.pdf",
        checksum="hash-chem-adv",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    run_chem = ProcessingRun.objects.create(
        resource=res_chem,
        library=library_a,
        source_checksum=res_chem.checksum,
        pipeline_version="1",
        extractor_version="1",
        chunker_version="1",
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        embedding_dimensions=provider.dimensions,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    DocumentStructureNode.objects.create(
        processing_run=run_chem,
        resource=res_chem,
        library=library_a,
        title="Chapter 14: Chemical Kinetics and Reaction Rates",
        normalized_title="chapter 14: chemical kinetics and reaction rates",
        level=1,
        page_start=100,
        page_end=150,
        sequence=0,
    )

    # Resource B: College Physics
    res_phys = Resource.objects.create(
        library=library_a,
        name="College Physics",
        resource_type=ResourceType.PDF,
        original_filename="phys.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/phys_adv.pdf",
        checksum="hash-phys-adv",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    run_phys = ProcessingRun.objects.create(
        resource=res_phys,
        library=library_a,
        source_checksum=res_phys.checksum,
        pipeline_version="1",
        extractor_version="1",
        chunker_version="1",
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        embedding_dimensions=provider.dimensions,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    DocumentStructureNode.objects.create(
        processing_run=run_phys,
        resource=res_phys,
        library=library_a,
        title="Chapter 8: Heat Transfer and Rate of Heat Flow",
        normalized_title="chapter 8: heat transfer and rate of heat flow",
        level=1,
        page_start=200,
        page_end=250,
        sequence=0,
    )

    # Resource C: Biology
    res_bio = Resource.objects.create(
        library=library_a,
        name="Cell Biology",
        resource_type=ResourceType.PDF,
        original_filename="bio.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/bio_adv.pdf",
        checksum="hash-bio-adv",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    run_bio = ProcessingRun.objects.create(
        resource=res_bio,
        library=library_a,
        source_checksum=res_bio.checksum,
        pipeline_version="1",
        extractor_version="1",
        chunker_version="1",
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        embedding_dimensions=provider.dimensions,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    DocumentStructureNode.objects.create(
        processing_run=run_bio,
        resource=res_bio,
        library=library_a,
        title="Chapter 5: Enzyme Activity and Temperature Effects",
        normalized_title="chapter 5: enzyme activity and temperature effects",
        level=1,
        page_start=50,
        page_end=80,
        sequence=0,
    )

    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)

    # Query 1: Reaction rate -> Chemistry dominates
    prior1 = find_candidate_resources("Why does increasing temperature increase reaction rate?", scope)
    assert prior1.prioritized_resource_ids == (res_chem.id,)

    # Query 2: Heat transfer -> Physics dominates
    prior2 = find_candidate_resources("How does temperature affect heat transfer?", scope)
    assert prior2.prioritized_resource_ids == (res_phys.id,)

    # Query 3: Enzyme activity -> Biology dominates
    prior3 = find_candidate_resources("How does temperature affect enzyme activity?", scope)
    assert prior3.prioritized_resource_ids == (res_bio.id,)


# ==============================================================================
# 3. RETRIEVAL BEHAVIOR ADVERSARIAL TESTS (SECTION 21, TESTS 16-20 & SECTION 23)
# ==============================================================================

@pytest.mark.django_db
def test_adversarial_definitional_vs_procedural_ranking(
    db,
    library_a: Library,
    user_a: User,
    membership_a: Membership,
    library_student_policy_a: LibraryAccessPolicy,
) -> None:
    """Section 23: 'What is activation energy?' (A > B/C/D) vs 'How do you calculate activation energy?' (D > A/B/C)."""
    provider = get_embedding_provider()
    res = Resource.objects.create(
        library=library_a,
        name="General Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="chem.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem_ea.pdf",
        checksum="hash-chem-ea",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    run = ProcessingRun.objects.create(
        resource=res,
        library=library_a,
        source_checksum=res.checksum,
        pipeline_version="1",
        extractor_version="1",
        chunker_version="1",
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        embedding_dimensions=provider.dimensions,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    node = DocumentStructureNode.objects.create(
        processing_run=run,
        resource=res,
        library=library_a,
        title="Chapter 14: Chemical Kinetics",
        normalized_title="chapter 14: chemical kinetics",
        level=1,
        page_start=1,
        page_end=50,
        sequence=0,
    )

    # Chunk A: Formal definition
    cA = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=1,
        text="Activation energy is defined as the minimum energy required to start a chemical reaction.",
        token_count=15,
        char_start=0,
        char_end=100,
        page_start=15,
        page_end=15,
        structure_node=node,
        section="Chapter 14: Chemical Kinetics",
        content_sha256="hash-cA",
    )
    ChunkEmbedding.objects.create(
        chunk=cA,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    # Chunk B: Passing discussion
    cB = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=2,
        text="The reaction proceeds slowly because the activation energy barrier is high at room temperature.",
        token_count=15,
        char_start=110,
        char_end=200,
        page_start=16,
        page_end=16,
        structure_node=node,
        section="Chapter 14: Chemical Kinetics",
        content_sha256="hash-cB",
    )
    ChunkEmbedding.objects.create(
        chunk=cB,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    # Chunk C: Arrhenius context
    cC = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=3,
        text="The activation energy appears in the Arrhenius equation as the exponential factor k = A * exp(-Ea/RT).",
        token_count=17,
        char_start=210,
        char_end=310,
        page_start=17,
        page_end=17,
        structure_node=node,
        section="Chapter 14: Chemical Kinetics",
        content_sha256="hash-cC",
    )
    ChunkEmbedding.objects.create(
        chunk=cC,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    # Chunk D: Calculation / Procedure
    cD = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=4,
        text="Activation energy can be calculated experimentally: Step 1: Measure k at multiple temperatures. Step 2: Plot ln(k) vs 1/T. Step 3: Calculate slope = -Ea/R.",
        token_count=26,
        char_start=320,
        char_end=480,
        page_start=18,
        page_end=18,
        structure_node=node,
        section="Chapter 14: Chemical Kinetics",
        content_sha256="hash-cD",
    )
    ChunkEmbedding.objects.create(
        chunk=cD,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    client = APIClient()
    token = mint_delegated_token(user_id=user_a.pk)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    # Test 1: "What is activation energy?" -> A ranks #1
    resp1 = client.post("/api/v1/knowledge/search/", {"query": "What is activation energy?", "top_k": 4}, format="json")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["results"][0]["chunk_id"] == str(cA.id)

    # Test 2: "How do you calculate activation energy?" -> D ranks #1
    resp2 = client.post("/api/v1/knowledge/search/", {"query": "How do you calculate activation energy?", "top_k": 4}, format="json")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["results"][0]["chunk_id"] == str(cD.id)


@pytest.mark.django_db
def test_overview_intent_favors_introductory_chapter_summary(
    db,
    library_a: Library,
    user_a: User,
    membership_a: Membership,
    library_student_policy_a: LibraryAccessPolicy,
) -> None:
    """Test 18: 'Explain photosynthesis.' favors chapter overview over deep leaf mechanisms."""
    provider = get_embedding_provider()
    res = Resource.objects.create(
        library=library_a,
        name="Biology 12",
        resource_type=ResourceType.PDF,
        original_filename="bio12.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/bio_photo.pdf",
        checksum="hash-bio-photo",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    run = ProcessingRun.objects.create(
        resource=res,
        library=library_a,
        source_checksum=res.checksum,
        pipeline_version="1",
        extractor_version="1",
        chunker_version="1",
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        embedding_dimensions=provider.dimensions,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    node_intro = DocumentStructureNode.objects.create(
        processing_run=run,
        resource=res,
        library=library_a,
        title="Chapter 8: Overview of Photosynthesis",
        normalized_title="chapter 8: overview of photosynthesis",
        level=1,
        page_start=100,
        page_end=105,
        sequence=0,
    )
    c_intro = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=1,
        text="In this chapter, an overview of photosynthesis describes how autotrophs transform solar radiant energy into stable chemical bonds.",
        token_count=18,
        char_start=0,
        char_end=120,
        page_start=100,
        page_end=100,
        structure_node=node_intro,
        section="Chapter 8: Overview of Photosynthesis",
        content_sha256="hash-intro",
    )
    ChunkEmbedding.objects.create(
        chunk=c_intro,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    client = APIClient()
    token = mint_delegated_token(user_id=user_a.pk)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.post("/api/v1/knowledge/search/", {"query": "Explain photosynthesis.", "top_k": 2}, format="json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["chunk_id"] == str(c_intro.id)
    assert data["metadata"]["query_intent"] == "overview"


@pytest.mark.django_db
def test_comparative_intent_favors_chunks_covering_both_entities(
    db,
    library_a: Library,
    user_a: User,
    membership_a: Membership,
    library_student_policy_a: LibraryAccessPolicy,
) -> None:
    """Test 20: 'Compare homogeneous and heterogeneous catalysts' favors passage discussing both."""
    provider = get_embedding_provider()
    res = Resource.objects.create(
        library=library_a,
        name="General Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="chem_comp.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem_comp.pdf",
        checksum="hash-chem-comp",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    run = ProcessingRun.objects.create(
        resource=res,
        library=library_a,
        source_checksum=res.checksum,
        pipeline_version="1",
        extractor_version="1",
        chunker_version="1",
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        embedding_dimensions=provider.dimensions,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    node = DocumentStructureNode.objects.create(
        processing_run=run,
        resource=res,
        library=library_a,
        title="Chapter 14: Catalysis",
        normalized_title="chapter 14: catalysis",
        level=1,
        page_start=1,
        page_end=50,
        sequence=0,
    )

    # Chunk 1: Mentions only homogeneous
    c1 = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=1,
        text="A homogeneous catalyst exists in the same phase as the reacting molecules, typically in liquid solution.",
        token_count=16,
        char_start=0,
        char_end=110,
        page_start=10,
        page_end=10,
        structure_node=node,
        section="Chapter 14: Catalysis",
        content_sha256="hash-c1",
    )
    ChunkEmbedding.objects.create(
        chunk=c1,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    # Chunk 2: Explicit comparison discussing both
    c2 = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=2,
        text="In contrast, while a homogeneous catalyst exists in the same phase, a heterogeneous catalyst exists in a different phase, offering distinct separation advantages.",
        token_count=23,
        char_start=120,
        char_end=280,
        page_start=11,
        page_end=11,
        structure_node=node,
        section="Chapter 14: Catalysis",
        content_sha256="hash-c2",
    )
    ChunkEmbedding.objects.create(
        chunk=c2,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    client = APIClient()
    token = mint_delegated_token(user_id=user_a.pk)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.post("/api/v1/knowledge/search/", {"query": "Compare homogeneous and heterogeneous catalysts.", "top_k": 2}, format="json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["chunk_id"] == str(c2.id)
    assert data["metadata"]["query_intent"] == "comparative"


@pytest.mark.django_db
def test_resource_partial_title_match(db, library_a: Library, user_a: User) -> None:
    """Test 3: Partial resource title overlap prioritizes matching textbook over generic title."""
    res_chem = Resource.objects.create(
        library=library_a,
        name="Organic Chemistry Principles",
        resource_type=ResourceType.PDF,
        original_filename="orgchem.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/orgchem.pdf",
        checksum="hash-orgchem",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    ProcessingRun.objects.create(
        resource=res_chem,
        library=library_a,
        source_checksum=res_chem.checksum,
        pipeline_version="1",
        extractor_version="1",
        chunker_version="1",
        embedding_model="fake-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    res_math = Resource.objects.create(
        library=library_a,
        name="Calculus Concepts",
        resource_type=ResourceType.PDF,
        original_filename="calc.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/calc.pdf",
        checksum="hash-calc",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    ProcessingRun.objects.create(
        resource=res_math,
        library=library_a,
        source_checksum=res_math.checksum,
        pipeline_version="1",
        extractor_version="1",
        chunker_version="1",
        embedding_model="fake-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
        is_active=True,
    )

    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    ranked = rank_candidate_resources("organic reaction mechanisms", scope)
    assert ranked[0].resource_id == res_chem.id
    assert ranked[0].score >= 4.0


@pytest.mark.django_db
def test_cross_library_authorization_isolation(
    db,
    library_a: Library,
    library_b: Library,
    user_a: User,
    membership_a: Membership,
    library_student_policy_a: LibraryAccessPolicy,
) -> None:
    """Test 6 & Section 19: Matching book in Library B never leaks to user authorized only for Library A."""
    provider = get_embedding_provider()

    # Library B contains matching chemistry textbook
    res_b = Resource.objects.create(
        library=library_b,
        name="General Chemistry Library B",
        resource_type=ResourceType.PDF,
        original_filename="chem_b.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_b/chem.pdf",
        checksum="hash-chem-b",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    run_b = ProcessingRun.objects.create(
        resource=res_b,
        library=library_b,
        source_checksum=res_b.checksum,
        pipeline_version="1",
        extractor_version="1",
        chunker_version="1",
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        embedding_dimensions=provider.dimensions,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    cB = DocumentChunk.objects.create(
        processing_run=run_b,
        library=library_b,
        resource=res_b,
        sequence=1,
        text="Activation energy in Library B secret document.",
        token_count=10,
        char_start=0,
        char_end=50,
        page_start=1,
        page_end=1,
        content_sha256="hash-cb-chunk",
    )
    ChunkEmbedding.objects.create(
        chunk=cB,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    # Library A has a general physics book
    res_a = Resource.objects.create(
        library=library_a,
        name="Physics Library A",
        resource_type=ResourceType.PDF,
        original_filename="phys_a.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/phys.pdf",
        checksum="hash-phys-a",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    run_a = ProcessingRun.objects.create(
        resource=res_a,
        library=library_a,
        source_checksum=res_a.checksum,
        pipeline_version="1",
        extractor_version="1",
        chunker_version="1",
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        embedding_dimensions=provider.dimensions,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    cA = DocumentChunk.objects.create(
        processing_run=run_a,
        library=library_a,
        resource=res_a,
        sequence=1,
        text="Physics concepts in Library A.",
        token_count=5,
        char_start=0,
        char_end=30,
        page_start=1,
        page_end=1,
        content_sha256="hash-ca-chunk",
    )
    ChunkEmbedding.objects.create(
        chunk=cA,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    client = APIClient()
    token = mint_delegated_token(user_id=user_a.pk)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.post("/api/v1/knowledge/search/", {"query": "Activation energy in General Chemistry", "top_k": 5}, format="json")
    assert resp.status_code == 200
    data = resp.json()
    for item in data["results"]:
        assert item["provenance"]["library_id"] == str(library_a.id)
        assert item["provenance"]["resource_id"] != str(res_b.id)


@pytest.mark.django_db
def test_causal_intent_favors_mechanistic_explanation(
    db,
    library_a: Library,
    user_a: User,
    membership_a: Membership,
    library_student_policy_a: LibraryAccessPolicy,
) -> None:
    """Test 19: 'Why does temperature increase reaction rate?' favors mechanistic/causal evidence."""
    provider = get_embedding_provider()
    res = Resource.objects.create(
        library=library_a,
        name="Physical Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="pchem.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/pchem_causal.pdf",
        checksum="hash-pchem-causal",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    run = ProcessingRun.objects.create(
        resource=res,
        library=library_a,
        source_checksum=res.checksum,
        pipeline_version="1",
        extractor_version="1",
        chunker_version="1",
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        embedding_dimensions=provider.dimensions,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    node = DocumentStructureNode.objects.create(
        processing_run=run,
        resource=res,
        library=library_a,
        title="Chapter 14: Reaction Kinetics and Mechanism",
        normalized_title="chapter 14: reaction kinetics and mechanism",
        level=1,
        page_start=1,
        page_end=50,
        sequence=0,
    )

    # Chunk 1: Passing mention
    c1 = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=1,
        text="A high reaction rate was observed when the temperature was kept at 50 degrees Celsius.",
        token_count=16,
        char_start=0,
        char_end=95,
        page_start=10,
        page_end=10,
        structure_node=node,
        section="Chapter 14: Reaction Kinetics and Mechanism",
        content_sha256="hash-c1-causal",
    )
    ChunkEmbedding.objects.create(
        chunk=c1,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    # Chunk 2: Causal mechanism
    c2 = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=2,
        text="Increasing temperature increases reaction rate because average molecular kinetic energy increases, which causes collision frequency and the fraction of molecules exceeding activation energy to rise.",
        token_count=27,
        char_start=100,
        char_end=300,
        page_start=11,
        page_end=11,
        structure_node=node,
        section="Chapter 14: Reaction Kinetics and Mechanism",
        content_sha256="hash-c2-causal",
    )
    ChunkEmbedding.objects.create(
        chunk=c2,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    client = APIClient()
    token = mint_delegated_token(user_id=user_a.pk)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.post("/api/v1/knowledge/search/", {"query": "Why does temperature increase reaction rate?", "top_k": 2}, format="json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["chunk_id"] == str(c2.id)
    assert data["metadata"]["query_intent"] == "causal"

