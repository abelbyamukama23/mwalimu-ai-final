"""Tests for Stage 8: Concept Normalization & Adaptive Retrieval Hardening."""

from __future__ import annotations

import uuid
import pytest
from rest_framework.test import APIClient

from platform_api.apps.knowledge.authentication import mint_delegated_token
from platform_api.apps.knowledge.concept_normalization import (
    TECHNICAL_ALIAS_REGISTRY,
    ConceptNormalizationResult,
    extract_query_concepts,
    normalize_token_morphology,
)
from platform_api.apps.knowledge.context_expansion import expand_retrieval_context
from platform_api.apps.knowledge.dto import ProvenanceDTO, SearchResultItemDTO
from platform_api.apps.knowledge.index_search import find_candidate_index_pages
from platform_api.apps.knowledge.policies import EffectiveRetrievalScope
from platform_api.apps.knowledge.query_intent import QueryIntent, QueryIntentResult, detect_query_intent
from platform_api.apps.knowledge.structure_search import find_candidate_structure_nodes
from platform_api.apps.libraries.models import Library, LibraryAccessPolicy
from platform_api.apps.memberships.models import Membership
from platform_api.apps.processing.embedding import get_embedding_provider
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
# 1. UNIT TESTS: MORPHOLOGY & ALIASES (SECTION 16A, 16B, 16C)
# ==============================================================================

def test_morphological_normalization_basic() -> None:
    """Test conservative English scientific morphological normalization."""
    # catalyst, catalysts, catalysis
    variants_cat = normalize_token_morphology("catalysts")
    assert "catalyst" in variants_cat
    assert "catalysis" in variants_cat

    # reaction, reactions
    variants_rxn = normalize_token_morphology("reactions")
    assert "reaction" in variants_rxn

    # equations -> equation
    variants_eq = normalize_token_morphology("equations")
    assert "equation" in variants_eq

    # molecules -> molecule
    variants_mol = normalize_token_morphology("molecules")
    assert "molecule" in variants_mol

    # temperatures -> temperature
    variants_temp = normalize_token_morphology("temperatures")
    assert "temperature" in variants_temp


def test_technical_aliases_activation_energy_and_equilibrium() -> None:
    """Ea, E_a, Eₐ resolve to 'activation energy'; Kc, K_c resolve to 'equilibrium constant'."""
    res1 = extract_query_concepts("What is Ea?")
    assert "activation energy" in res1.canonical_concepts
    assert ("ea", "activation energy") in res1.aliases_applied

    res2 = extract_query_concepts("Calculate E_a for the reaction")
    assert "activation energy" in res2.canonical_concepts

    res3 = extract_query_concepts("What is Eₐ?")
    assert "activation energy" in res3.canonical_concepts

    res4 = extract_query_concepts("Find the value of Kc.")
    assert "equilibrium constant" in res4.canonical_concepts

    res5 = extract_query_concepts("Explain K_c in chemical equilibrium")
    assert "equilibrium constant" in res5.canonical_concepts


def test_false_normalization_resistance() -> None:
    """Distinct technical concepts must NOT be collapsed together."""
    # Ka, Ksp, Kw, Kp must NOT become equilibrium constant (Kc)
    res_ka = extract_query_concepts("What is Ka for acetic acid?")
    assert "equilibrium constant" not in res_ka.canonical_concepts
    assert ("ka", "equilibrium constant") not in res_ka.aliases_applied

    res_ksp = extract_query_concepts("Calculate Ksp for silver chloride")
    assert "equilibrium constant" not in res_ksp.canonical_concepts

    # organ must NOT become organic, relativity must NOT become relative
    assert "organic" not in normalize_token_morphology("organ")
    assert "organ" not in normalize_token_morphology("organic")
    assert "relativity" not in normalize_token_morphology("relative")
    assert "relative" not in normalize_token_morphology("relativity")
    assert "mass" in normalize_token_morphology("mass")
    assert "gas" in normalize_token_morphology("gas")


def test_query_concept_extraction_does_not_fabricate() -> None:
    """Concepts not mentioned or aliased are NEVER fabricated."""
    res = extract_query_concepts("Why does a catalyst make a reaction faster?")
    # 'catalyst' and 'reaction' should be extracted
    assert any("catalyst" in t for t in res.normalized_terms)
    assert any("reaction" in t for t in res.normalized_terms)
    # 'activation energy' must NOT be fabricated
    assert "activation energy" not in res.canonical_concepts


# ==============================================================================
# 2. INTEGRATION TESTS: TOC & INDEX NORMALIZATION (SECTION 16D, 16E, 16F)
# ==============================================================================

@pytest.mark.django_db
def test_toc_normalization_catalyst_discovers_catalysis(
    db,
    library_a: Library,
    user_a: User,
) -> None:
    """Case 1: Query 'Why do catalysts increase reaction rate?' matches TOC 'Catalysis'."""
    res = Resource.objects.create(
        library=library_a,
        name="General Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="chem.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem_toc.pdf",
        checksum="hash-chem-toc",
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
        embedding_model="fake-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    node_catalysis = DocumentStructureNode.objects.create(
        processing_run=run,
        resource=res,
        library=library_a,
        title="Chapter 14.5: Catalysis",
        normalized_title="chapter 14.5: catalysis",
        level=2,
        page_start=50,
        page_end=60,
        sequence=1,
    )

    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    candidates = find_candidate_structure_nodes("Why do catalysts increase reaction rate?", scope)
    assert node_catalysis.id in candidates


@pytest.mark.django_db
def test_toc_normalization_ea_discovers_activation_energy(
    db,
    library_a: Library,
    user_a: User,
) -> None:
    """Case 2: Query 'What is Ea?' matches TOC 'Activation Energy and Arrhenius Equation'."""
    res = Resource.objects.create(
        library=library_a,
        name="General Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="chem_ea.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem_ea.pdf",
        checksum="hash-chem-ea-toc",
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
        embedding_model="fake-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    node_ea = DocumentStructureNode.objects.create(
        processing_run=run,
        resource=res,
        library=library_a,
        title="14.4 Activation Energy and Arrhenius Equation",
        normalized_title="14.4 activation energy and arrhenius equation",
        level=2,
        page_start=40,
        page_end=49,
        sequence=1,
    )

    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    candidates = find_candidate_structure_nodes("What is Ea?", scope)
    assert node_ea.id in candidates


@pytest.mark.django_db
def test_index_normalization_catalyst_discovers_catalysis_and_catalysts(
    db,
    library_a: Library,
    user_a: User,
) -> None:
    """Index lookup matches BookIndexEntry 'catalysis' from query 'catalyst'."""
    res = Resource.objects.create(
        library=library_a,
        name="General Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="chem_idx.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem_idx.pdf",
        checksum="hash-chem-idx",
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
        embedding_model="fake-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    entry = BookIndexEntry.objects.create(
        processing_run=run,
        resource=res,
        term="Catalysis",
        normalized_term="catalysis",
        raw_page_references="55, 56",
        target_physical_pages=[55, 56],
    )


    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    pages = find_candidate_index_pages("How does a catalyst work?", scope)
    assert 55 in pages
    assert 56 in pages


@pytest.mark.django_db
def test_index_normalization_multi_concept_intersection_preserved(
    db,
    library_a: Library,
    user_a: User,
) -> None:
    """Multi-concept intersection still prioritizes overlapping pages after normalization."""
    res = Resource.objects.create(
        library=library_a,
        name="General Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="chem_int.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem_int.pdf",
        checksum="hash-chem-int",
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
        embedding_model="fake-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    # Concept 1: catalysts (pages 20, 25, 30)
    BookIndexEntry.objects.create(
        processing_run=run,
        resource=res,
        term="Catalysts",
        normalized_term="catalysts",
        raw_page_references="20, 25, 30",
        target_physical_pages=[20, 25, 30],
    )
    # Concept 2: reaction rates (pages 25, 40)
    BookIndexEntry.objects.create(
        processing_run=run,
        resource=res,
        term="Reaction rates",
        normalized_term="reaction rates",
        raw_page_references="25, 40",
        target_physical_pages=[25, 40],
    )


    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    pages = find_candidate_index_pages("Effect of catalyst on reaction rate", scope)
    # Page 25 is the intersection
    assert pages[0] == 25


# ==============================================================================
# 3. ADAPTIVE CONTEXT EXPANSION TESTS (SECTION 16H, 16I, 16J)
# ==============================================================================

@pytest.mark.django_db
def test_procedural_adaptive_context_expansion_expands_to_2(
    db,
    library_a: Library,
    user_a: User,
) -> None:
    """Section 16H & Case 4: Procedural query with calculation evidence expands sequence ±2."""
    res = Resource.objects.create(
        library=library_a,
        name="General Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="chem_calc.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem_calc.pdf",
        checksum="hash-chem-calc",
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
        embedding_model="fake-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    node = DocumentStructureNode.objects.create(
        processing_run=run,
        resource=res,
        library=library_a,
        title="Chapter 14.4: Determining Activation Energy",
        normalized_title="chapter 14.4: determining activation energy",
        level=2,
        page_start=1,
        page_end=10,
        sequence=1,
    )

    chunks = []
    for seq in range(1, 6):
        c = DocumentChunk.objects.create(
            processing_run=run,
            library=library_a,
            resource=res,
            sequence=seq,
            text=f"Step {seq}: Worked example for calculating activation energy with experimental values. Formula: k = A * exp(-Ea/RT).",
            token_count=20,
            char_start=(seq - 1) * 100,
            char_end=seq * 100,
            page_start=seq,
            page_end=seq,
            structure_node=node,
            section="Chapter 14.4: Determining Activation Energy",
            content_sha256=f"hash-seq-{seq}",
        )
        chunks.append(c)

    # Core result is chunk 3 (middle of worked example)
    core_item = SearchResultItemDTO(
        chunk_id=chunks[2].id,
        score=0.90,
        text=chunks[2].text,
        provenance=ProvenanceDTO(
            resource_id=res.id,
            resource_name=res.name,
            library_id=library_a.id,
            library_name=library_a.name,
            page_start=3,
            page_end=3,
            section="Chapter 14.4: Determining Activation Energy",
            sequence=3,
            char_start=200,
            char_end=300,
            content_sha256="hash-seq-3",
        ),
    )

    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    procedural_intent = QueryIntentResult(
        intent=QueryIntent.PROCEDURAL,
        confidence=0.95,
        matched_cue="how do i calculate",
    )

    expanded = expand_retrieval_context(
        core_results=[core_item],
        scope=scope,
        context_window=1,
        query_intent=procedural_intent,
    )

    # Sequence ±2 should retrieve chunks 1, 2, 3, 4, 5!
    expanded_seqs = [item.provenance.sequence for item in expanded]
    assert 1 in expanded_seqs
    assert 2 in expanded_seqs
    assert 3 in expanded_seqs
    assert 4 in expanded_seqs
    assert 5 in expanded_seqs
    assert len(expanded) == 5
    # Core chunk remains #1
    assert expanded[0].chunk_id == core_item.chunk_id


@pytest.mark.django_db
def test_default_context_expansion_retains_1_for_conceptual(
    db,
    library_a: Library,
    user_a: User,
) -> None:
    """Section 16I: Conceptual queries without procedural markers retain default sequence ±1."""
    res = Resource.objects.create(
        library=library_a,
        name="General Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="chem_conc.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem_conc.pdf",
        checksum="hash-chem-conc",
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
        embedding_model="fake-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    node = DocumentStructureNode.objects.create(
        processing_run=run,
        resource=res,
        library=library_a,
        title="Chapter 14: Reaction Rates",
        normalized_title="chapter 14: reaction rates",
        level=1,
        page_start=1,
        page_end=10,
        sequence=1,
    )

    chunks = []
    for seq in range(1, 6):
        c = DocumentChunk.objects.create(
            processing_run=run,
            library=library_a,
            resource=res,
            sequence=seq,
            text=f"Conceptual narrative discussion about collision theory {seq}.",
            token_count=10,
            char_start=(seq - 1) * 50,
            char_end=seq * 50,
            page_start=seq,
            page_end=seq,
            structure_node=node,
            section="Chapter 14: Reaction Rates",
            content_sha256=f"hash-conc-{seq}",
        )
        chunks.append(c)

    core_item = SearchResultItemDTO(
        chunk_id=chunks[2].id,
        score=0.88,
        text=chunks[2].text,
        provenance=ProvenanceDTO(
            resource_id=res.id,
            resource_name=res.name,
            library_id=library_a.id,
            library_name=library_a.name,
            page_start=3,
            page_end=3,
            section="Chapter 14: Reaction Rates",
            sequence=3,
            char_start=100,
            char_end=150,
            content_sha256="hash-conc-3",
        ),
    )

    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    conceptual_intent = QueryIntentResult(
        intent=QueryIntent.CONCEPTUAL,
        confidence=0.85,
        matched_cue="why does",
    )

    expanded = expand_retrieval_context(
        core_results=[core_item],
        scope=scope,
        context_window=1,
        query_intent=conceptual_intent,
    )

    # Sequence ±1: chunks 2, 3, 4 (3 chunks total)
    expanded_seqs = [item.provenance.sequence for item in expanded]
    assert 2 in expanded_seqs
    assert 3 in expanded_seqs
    assert 4 in expanded_seqs
    assert 1 not in expanded_seqs
    assert 5 not in expanded_seqs
    assert len(expanded) == 3


@pytest.mark.django_db
def test_adaptive_expansion_strictly_bounded_by_section_and_structure_node(
    db,
    library_a: Library,
    user_a: User,
) -> None:
    """Section 16J: Sequence ±2 cannot cross section boundaries or structure node boundaries."""
    res = Resource.objects.create(
        library=library_a,
        name="General Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="chem_bound.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem_bound.pdf",
        checksum="hash-chem-bound",
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
        embedding_model="fake-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    node1 = DocumentStructureNode.objects.create(
        processing_run=run,
        resource=res,
        library=library_a,
        title="Chapter 13: Solutions",
        normalized_title="chapter 13: solutions",
        level=1,
        page_start=1,
        page_end=10,
        sequence=1,
    )
    node2 = DocumentStructureNode.objects.create(
        processing_run=run,
        resource=res,
        library=library_a,
        title="Chapter 14: Chemical Kinetics",
        normalized_title="chapter 14: chemical kinetics",
        level=1,
        page_start=11,
        page_end=20,
        sequence=2,
    )

    # Chunk 1 belongs to Chapter 13
    c1 = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=1,
        text="Chapter 13 ending comments on solution concentration.",
        token_count=10,
        char_start=0,
        char_end=50,
        page_start=10,
        page_end=10,
        structure_node=node1,
        section="Chapter 13: Solutions",
        content_sha256="hash-b-1",
    )
    # Chunk 2 belongs to Chapter 14 (Worked example start)
    c2 = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=2,
        text="Worked example step 1: Calculate rate constant from experimental data table.",
        token_count=12,
        char_start=60,
        char_end=120,
        page_start=11,
        page_end=11,
        structure_node=node2,
        section="Chapter 14: Chemical Kinetics",
        content_sha256="hash-b-2",
    )
    # Chunk 3 belongs to Chapter 14
    c3 = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=3,
        text="Step 2: Substitute values into Arrhenius formula.",
        token_count=10,
        char_start=130,
        char_end=180,
        page_start=12,
        page_end=12,
        structure_node=node2,
        section="Chapter 14: Chemical Kinetics",
        content_sha256="hash-b-3",
    )

    core_item = SearchResultItemDTO(
        chunk_id=c2.id,
        score=0.92,
        text=c2.text,
        provenance=ProvenanceDTO(
            resource_id=res.id,
            resource_name=res.name,
            library_id=library_a.id,
            library_name=library_a.name,
            page_start=11,
            page_end=11,
            section="Chapter 14: Chemical Kinetics",
            sequence=2,
            char_start=60,
            char_end=120,
            content_sha256="hash-b-2",
        ),
    )

    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    procedural_intent = QueryIntentResult(
        intent=QueryIntent.PROCEDURAL,
        confidence=0.95,
        matched_cue="how to calculate",
    )

    expanded = expand_retrieval_context(
        core_results=[core_item],
        scope=scope,
        context_window=1,
        query_intent=procedural_intent,
    )

    expanded_chunk_ids = [item.chunk_id for item in expanded]
    # Chunk 3 is in same section -> included
    assert c3.id in expanded_chunk_ids
    # Chunk 1 is across Chapter 13 section boundary -> MUST NOT be included!
    assert c1.id not in expanded_chunk_ids


# ==============================================================================
# 4. END-TO-END ADVERSARIAL & SECURITY TESTS (SECTION 16K, 17)
# ==============================================================================

@pytest.mark.django_db
def test_cross_library_concept_normalization_adversarial_isolation(
    db,
    library_a: Library,
    library_b: Library,
    user_a: User,
    membership_a: Membership,
    library_student_policy_a: LibraryAccessPolicy,
) -> None:
    """Section 16K: Matching normalized term in Library B cannot leak to User A in Library A."""
    provider = get_embedding_provider()

    # Library B has Catalysis resource
    res_b = Resource.objects.create(
        library=library_b,
        name="Advanced Catalysis Research Library B",
        resource_type=ResourceType.PDF,
        original_filename="cat_b.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_b/cat.pdf",
        checksum="hash-cat-b",
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
    cb = DocumentChunk.objects.create(
        processing_run=run_b,
        library=library_b,
        resource=res_b,
        sequence=1,
        text="Industrial catalysis secret methods in Library B.",
        token_count=8,
        char_start=0,
        char_end=50,
        page_start=1,
        page_end=1,
        content_sha256="hash-cb-cat",
    )
    ChunkEmbedding.objects.create(
        chunk=cb,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    # Library A has standard chemistry
    res_a = Resource.objects.create(
        library=library_a,
        name="General Chemistry Library A",
        resource_type=ResourceType.PDF,
        original_filename="chem_a.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem.pdf",
        checksum="hash-chem-a",
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
    ca = DocumentChunk.objects.create(
        processing_run=run_a,
        library=library_a,
        resource=res_a,
        sequence=1,
        text="Catalysts speed up reactions by lowering activation energy.",
        token_count=9,
        char_start=0,
        char_end=60,
        page_start=1,
        page_end=1,
        content_sha256="hash-ca-cat",
    )
    ChunkEmbedding.objects.create(
        chunk=ca,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    client = APIClient()
    token = mint_delegated_token(user_id=user_a.pk)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.post("/api/v1/knowledge/search/", {"query": "How do catalysts work?", "top_k": 5}, format="json")
    assert resp.status_code == 200
    data = resp.json()
    for item in data["results"]:
        assert item["provenance"]["library_id"] == str(library_a.id)
        assert item["provenance"]["resource_id"] != str(res_b.id)


@pytest.mark.django_db
def test_end_to_end_search_with_stage8_metadata(
    db,
    library_a: Library,
    user_a: User,
    membership_a: Membership,
    library_student_policy_a: LibraryAccessPolicy,
) -> None:
    """Verify additive Stage 8 metadata (concept_normalization_applied, adaptive_context_window)."""
    provider = get_embedding_provider()
    res = Resource.objects.create(
        library=library_a,
        name="General Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="chem_meta.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem_meta.pdf",
        checksum="hash-chem-meta",
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
    c = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=1,
        text="Activation energy (Ea) determines reaction rate.",
        token_count=8,
        char_start=0,
        char_end=50,
        page_start=1,
        page_end=1,
        content_sha256="hash-meta-c",
    )
    ChunkEmbedding.objects.create(
        chunk=c,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    client = APIClient()
    token = mint_delegated_token(user_id=user_a.pk)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.post("/api/v1/knowledge/search/", {"query": "What is Ea?", "top_k": 2}, format="json")
    assert resp.status_code == 200
    data = resp.json()
    metadata = data["metadata"]
    assert metadata["concept_normalization_applied"] is True
    assert "activation energy" in metadata["normalized_concepts"]
    assert any(a["alias"] == "ea" and a["canonical"] == "activation energy" for a in metadata["aliases_applied"])
    assert "adaptive_context_window" in metadata
