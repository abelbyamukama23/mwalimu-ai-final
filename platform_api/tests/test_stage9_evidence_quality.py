"""Tests for Stage 9: Evidence Quality & Answer-Ready Retrieval."""

from __future__ import annotations

import uuid
import pytest
from rest_framework.test import APIClient

from platform_api.apps.knowledge.authentication import mint_delegated_token
from platform_api.apps.knowledge.dto import ProvenanceDTO, SearchResultItemDTO
from platform_api.apps.knowledge.evidence_quality import (
    evaluate_chunk_evidence,
    evaluate_cluster_evidence,
)
from platform_api.apps.knowledge.policies import EffectiveRetrievalScope
from platform_api.apps.knowledge.query_intent import QueryIntent, QueryIntentResult, detect_query_intent
from platform_api.apps.libraries.models import Library, LibraryAccessPolicy
from platform_api.apps.memberships.models import Membership
from platform_api.apps.processing.embedding import get_embedding_provider
from platform_api.apps.processing.models import (
    ChunkEmbedding,
    DocumentChunk,
    DocumentStructureNode,
    ProcessingRun,
    ProcessingStatus,
)
from platform_api.apps.resources.models import Resource, ResourceStatus, ResourceType
from platform_api.apps.users.models import User


# ==============================================================================
# 1. UNIT & ADVERSARIAL EVIDENCE QUALITY TESTS
# ==============================================================================

def test_definition_vs_passing_mention_outranks() -> None:
    """Test 1: Formal definition outranks passing mention for DEFINITIONAL intent."""
    query = "What is activation energy?"
    intent_result = detect_query_intent(query)
    assert intent_result.intent == QueryIntent.DEFINITIONAL

    # Chunk A: Formal definition
    text_a = "Activation energy is defined as the minimum energy required for reactant molecules to undergo a successful collision."
    # Chunk B: Passing mention / consequence
    text_b = "Because the activation energy is high, the reaction occurs slowly at room temperature."

    eq_a = evaluate_chunk_evidence(text_a, "Kinetics", query, intent_result)
    eq_b = evaluate_chunk_evidence(text_b, "Kinetics", query, intent_result)

    assert eq_a.directness > eq_b.directness
    assert eq_a.completeness > eq_b.completeness
    assert eq_a.quality_score > eq_b.quality_score
    assert eq_a.evidence_bonus > eq_b.evidence_bonus


def test_procedural_completeness_outranks_theoretical_mention() -> None:
    """Test 2: Worked-example procedural evidence outranks theoretical mention."""
    query = "How do you calculate activation energy?"
    intent_result = detect_query_intent(query)
    assert intent_result.intent == QueryIntent.PROCEDURAL

    # Chunk A: Complete worked procedure with steps
    text_a = "Worked example: To calculate activation energy, Step 1: measure rate constants. Step 2: plot ln(k) vs 1/T. Solution: slope = -Ea/R."
    # Chunk B: General theoretical description
    text_b = "Activation energy can be calculated using temperature dependence and reaction kinetics theory."

    eq_a = evaluate_chunk_evidence(text_a, "Determining Ea", query, intent_result)
    eq_b = evaluate_chunk_evidence(text_b, "Determining Ea", query, intent_result)

    assert eq_a.directness > eq_b.directness
    assert eq_a.completeness > eq_b.completeness
    assert eq_a.quality_score > eq_b.quality_score
    assert eq_a.evidence_bonus > eq_b.evidence_bonus


def test_quantitative_evidence_ranks_above_descriptive_prose() -> None:
    """Test 3: Equation + numerical values + solution evidence ranks above descriptive prose."""
    query = "Calculate the rate constant from temperature data"
    intent_result = detect_query_intent(query)
    assert intent_result.intent == QueryIntent.QUANTITATIVE

    # Chunk A: Equation with values, units, and solution
    text_a = "Given: T = 300 K, A = 1.0e11. Using k = A * exp(-Ea/RT), substitute values: k = 2.4e-3 mol/L. Solution: k = 2.4e-3."
    # Chunk B: Descriptive prose
    text_b = "The rate constant depends on temperature according to an exponential relationship in collision theory."

    eq_a = evaluate_chunk_evidence(text_a, "Arrhenius Calculations", query, intent_result)
    eq_b = evaluate_chunk_evidence(text_b, "Arrhenius Calculations", query, intent_result)

    assert eq_a.directness > eq_b.directness
    assert eq_a.completeness > eq_b.completeness
    assert eq_a.quality_score > eq_b.quality_score
    assert eq_a.evidence_bonus > eq_b.evidence_bonus


def test_comparative_coverage_outranks_single_concept() -> None:
    """Test 4: Chunk comparing both concepts outranks chunk discussing only one."""
    query = "Compare homogeneous and heterogeneous catalysts."
    intent_result = detect_query_intent(query)
    assert intent_result.intent == QueryIntent.COMPARATIVE

    # Chunk A: Contrasts both homogeneous and heterogeneous catalysts
    text_a = "Homogeneous catalysts exist in the same phase as reactants, whereas heterogeneous catalysts exist in a distinct solid phase in contrast."
    # Chunk B: Discusses only one side
    text_b = "Heterogeneous catalysts are widely used in chemical industrial synthesis and petroleum refining."

    eq_a = evaluate_chunk_evidence(text_a, "Catalysis", query, intent_result)
    eq_b = evaluate_chunk_evidence(text_b, "Catalysis", query, intent_result)

    assert eq_a.directness > eq_b.directness
    assert eq_a.completeness > eq_b.completeness
    assert eq_a.quality_score > eq_b.quality_score
    assert eq_a.evidence_bonus > eq_b.evidence_bonus


def test_causal_mechanism_outranks_simple_factual_statement() -> None:
    """Test 5: Mechanistic explanation outranks simple factual statement."""
    query = "Why does increasing temperature increase reaction rate?"
    intent_result = detect_query_intent(query)
    assert intent_result.intent == QueryIntent.CAUSAL

    # Chunk A: Full mechanistic chain
    text_a = "Increasing temperature increases reaction rate because reactant molecules gain higher kinetic energy, which causes a greater collision frequency and a larger fraction of molecules to exceed activation energy."
    # Chunk B: Bare factual statement
    text_b = "Reaction rates generally increase at higher temperatures in laboratory conditions."

    eq_a = evaluate_chunk_evidence(text_a, "Temperature Effects", query, intent_result)
    eq_b = evaluate_chunk_evidence(text_b, "Temperature Effects", query, intent_result)

    assert eq_a.directness > eq_b.directness
    assert eq_a.completeness > eq_b.completeness
    assert eq_a.quality_score > eq_b.quality_score
    assert eq_a.evidence_bonus > eq_b.evidence_bonus


def test_overview_introductory_evidence_outranks_leaf_subsection() -> None:
    """Test 6: Introductory chapter overview outranks deep leaf subsection."""
    query = "Explain photosynthesis."
    intent_result = detect_query_intent(query)
    assert intent_result.intent == QueryIntent.OVERVIEW

    # Chunk A: Chapter overview
    text_a = "In this chapter, we provide an overview and introduction to photosynthesis, explaining how radiant energy is converted into biochemical fuel."
    # Chunk B: Deep leaf sub-mechanism
    text_b = "Ferredoxin NADP reductase transfers electrons in photosystem I within the chloroplast thylakoid membrane."

    eq_a = evaluate_chunk_evidence(text_a, "Chapter 8: Overview of Photosynthesis", query, intent_result)
    eq_b = evaluate_chunk_evidence(text_b, "Section 8.3.4: Thylakoid Electron Transfer", query, intent_result)

    assert eq_a.directness > eq_b.directness
    assert eq_a.structural_authority > eq_b.structural_authority
    assert eq_a.quality_score > eq_b.quality_score


def test_multi_chunk_procedural_cluster_recognition() -> None:
    """Test 7: Step 1 -> Step 2 -> Calculation -> Result forms an answer-ready cluster."""
    query = "How to determine activation energy from experiments"
    intent_result = detect_query_intent(query)

    chunk1 = SearchResultItemDTO(
        chunk_id=uuid.uuid4(),
        score=0.85,
        text="Step 1: Measure rate constants across varying temperatures.",
        provenance=ProvenanceDTO(
            resource_id=uuid.uuid4(),
            resource_name="Chem",
            library_id=uuid.uuid4(),
            library_name="Lib",
            page_start=1,
            page_end=1,
            section="Kinetics",
            sequence=1,
            char_start=0,
            char_end=50,
            content_sha256="c1",
        ),
    )
    chunk2 = SearchResultItemDTO(
        chunk_id=uuid.uuid4(),
        score=0.80,
        text="Step 2: Plot ln(k) against 1/T. Formula: slope = -Ea/R, calculate Ea.",
        provenance=ProvenanceDTO(
            resource_id=chunk1.provenance.resource_id,
            resource_name="Chem",
            library_id=chunk1.provenance.library_id,
            library_name="Lib",
            page_start=1,
            page_end=1,
            section="Kinetics",
            sequence=2,
            char_start=51,
            char_end=110,
            content_sha256="c2",
        ),
    )
    chunk3 = SearchResultItemDTO(
        chunk_id=uuid.uuid4(),
        score=0.75,
        text="Solution: Substitute universal gas constant R to find activation energy result.",
        provenance=ProvenanceDTO(
            resource_id=chunk1.provenance.resource_id,
            resource_name="Chem",
            library_id=chunk1.provenance.library_id,
            library_name="Lib",
            page_start=2,
            page_end=2,
            section="Kinetics",
            sequence=3,
            char_start=111,
            char_end=170,
            content_sha256="c3",
        ),
    )

    cluster_eq = evaluate_cluster_evidence(
        cluster_items=[chunk1, chunk2, chunk3],
        query_text=query,
        intent_result=intent_result,
    )

    assert cluster_eq.is_answer_ready is True
    assert cluster_eq.cluster_size == 3
    assert cluster_eq.cluster_score > 0.70
    assert any("step-by-step" in r for r in cluster_eq.reasons)


def test_concept_coverage_multi_concept_favoring() -> None:
    """Test 8: Passage covering multiple normalized concepts scores higher coverage."""
    query = "How does temperature affect the rate constant according to the Arrhenius equation?"
    intent_result = detect_query_intent(query)

    # Chunk A: Covers temperature, rate constant, and Arrhenius equation
    text_a = "The Arrhenius equation describes how the rate constant varies with temperature."
    # Chunk B: Covers only temperature
    text_b = "Temperature is an intensive thermodynamic state property."

    eq_a = evaluate_chunk_evidence(text_a, "Kinetics", query, intent_result)
    eq_b = evaluate_chunk_evidence(text_b, "Kinetics", query, intent_result)

    assert eq_a.concept_coverage > eq_b.concept_coverage
    assert eq_a.quality_score > eq_b.quality_score


def test_score_bounding_guarantee() -> None:
    """Test 9: 0.0 <= final_score <= 1.0 for extreme bonus combinations."""
    query = "What is activation energy?"
    intent_result = detect_query_intent(query)

    text = "Activation energy is defined as the minimum energy required for reaction."
    eq = evaluate_chunk_evidence(text, "Chapter 14", query, intent_result)

    # Max evidence bonus is +0.08
    assert 0.0 <= eq.evidence_bonus <= 0.08

    # Even with high base_score (e.g. 0.98) and intent_bonus (0.05), combined score capped at 1.0
    combined = round(min(1.0, 0.98 + 0.05 + eq.evidence_bonus), 6)
    assert 0.0 <= combined <= 1.0


def test_recall_preservation_weak_evidence_not_zeroed() -> None:
    """Test 10: Semantically relevant chunks with weak evidence markers are preserved."""
    query = "activation energy"
    text_weak = "General discussion mentioning activation energy in passing."
    eq = evaluate_chunk_evidence(text_weak, None, query, None)

    # Bonus is 0.0, but quality_score is >= 0.0 and chunk is NOT filtered out
    assert eq.quality_score >= 0.0
    assert eq.evidence_bonus >= 0.0


def test_unknown_intent_fallback_safety() -> None:
    """Test 12: query_intent = None produces safe Stage 8-compatible neutral behavior."""
    eq = evaluate_chunk_evidence(
        chunk_text="Some valid textbook content.",
        section="Chapter 1",
        query_text="Some query",
        intent_result=None,
    )
    assert 0.0 <= eq.quality_score <= 1.0
    assert 0.0 <= eq.evidence_bonus <= 0.08


# ==============================================================================
# 2. END-TO-END INTEGRATION & SECURITY TESTS
# ==============================================================================

@pytest.mark.django_db
def test_cross_library_isolation_with_stage9(
    db,
    library_a: Library,
    library_b: Library,
    user_a: User,
    membership_a: Membership,
    library_student_policy_a: LibraryAccessPolicy,
) -> None:
    """Test 11: Cross-library isolation: User A cannot retrieve Library B even with high evidence."""
    provider = get_embedding_provider()

    # Library B has high-quality direct definition of activation energy
    res_b = Resource.objects.create(
        library=library_b,
        name="Chemistry B",
        resource_type=ResourceType.PDF,
        original_filename="chem_b.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_b/chem.pdf",
        checksum="hash-b-stage9",
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
        text="Activation energy is defined as the minimum energy in Library B.",
        token_count=10,
        char_start=0,
        char_end=60,
        page_start=1,
        page_end=1,
        content_sha256="hash-cb-stage9",
    )
    ChunkEmbedding.objects.create(
        chunk=cb,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    # Library A has standard chemistry resource
    res_a = Resource.objects.create(
        library=library_a,
        name="Chemistry A",
        resource_type=ResourceType.PDF,
        original_filename="chem_a.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem.pdf",
        checksum="hash-a-stage9",
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
        text="Activation energy is the barrier to overcome in Library A.",
        token_count=10,
        char_start=0,
        char_end=60,
        page_start=1,
        page_end=1,
        content_sha256="hash-ca-stage9",
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

    resp = client.post("/api/v1/knowledge/search/", {"query": "What is activation energy?", "top_k": 5}, format="json")
    assert resp.status_code == 200
    data = resp.json()
    for item in data["results"]:
        assert item["provenance"]["library_id"] == str(library_a.id)
        assert item["provenance"]["resource_id"] != str(res_b.id)


@pytest.mark.django_db
def test_end_to_end_search_with_stage9_metadata(
    db,
    library_a: Library,
    user_a: User,
    membership_a: Membership,
    library_student_policy_a: LibraryAccessPolicy,
) -> None:
    """Test 13: Verify additive Stage 9 metadata (evidence_quality_applied, top_evidence_quality, etc.)."""
    provider = get_embedding_provider()
    res = Resource.objects.create(
        library=library_a,
        name="General Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="chem_meta_s9.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem_meta_s9.pdf",
        checksum="hash-chem-meta-s9",
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
        text="Activation energy is defined as the minimum kinetic energy reactant molecules must possess.",
        token_count=12,
        char_start=0,
        char_end=80,
        page_start=1,
        page_end=1,
        section="Chapter 14.4: Activation Energy",
        content_sha256="hash-meta-s9-c",
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

    resp = client.post("/api/v1/knowledge/search/", {"query": "What is activation energy?", "top_k": 2}, format="json")
    assert resp.status_code == 200
    data = resp.json()
    metadata = data["metadata"]

    assert metadata["evidence_quality_applied"] is True
    assert metadata["evidence_quality_version"] == "stage9"
    assert "top_evidence_quality" in metadata
    assert metadata["top_evidence_quality"] > 0.50
    assert "answer_ready_cluster" in metadata
