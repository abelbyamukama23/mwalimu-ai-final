"""Tests for Stage 10: Citation Precision & Synthesized Evidence Assembly."""

from __future__ import annotations

import uuid
import pytest
from rest_framework.test import APIClient

from platform_api.apps.knowledge.authentication import mint_delegated_token
from platform_api.apps.knowledge.citation_assembly import (
    extract_answer_spans,
    resolve_chunk_citations,
    split_sentences_with_offsets,
    synthesize_derivation_cluster,
)
from platform_api.apps.knowledge.dto import ProvenanceDTO, SearchResultItemDTO
from platform_api.apps.knowledge.policies import EffectiveRetrievalScope
from platform_api.apps.knowledge.query_intent import QueryIntent, QueryIntentResult, detect_query_intent
from platform_api.apps.libraries.models import Library, LibraryAccessPolicy
from platform_api.apps.memberships.models import Membership
from platform_api.apps.processing.embedding import get_embedding_provider
from platform_api.apps.processing.models import (
    ChunkEmbedding,
    DocumentChunk,
    DocumentPageMap,
    DocumentStructureNode,
    ProcessingRun,
    ProcessingStatus,
)
from platform_api.apps.resources.models import Resource, ResourceStatus, ResourceType
from platform_api.apps.users.models import User


# ==============================================================================
# 1. UNIT TESTS: SPAN EXTRACTION & SENTENCE TOKENIZATION
# ==============================================================================

def test_sentence_splitting_abbreviations_and_decimals() -> None:
    """Protects common academic abbreviations (e.g., Fig., et al.) and decimals from false splits."""
    text = "According to Smith et al., the value of k is e.g. 3.14 mol/L. Fig. 1 shows the experimental curve."
    sentences = split_sentences_with_offsets(text)
    # Should split into exactly 2 sentences:
    # 1: "According to Smith et al., the value of k is e.g. 3.14 mol/L."
    # 2: "Fig. 1 shows the experimental curve."
    assert len(sentences) == 2
    assert "3.14 mol/L." in sentences[0][0]
    assert sentences[1][0] == "Fig. 1 shows the experimental curve."
    # Offsets must match exactly
    assert text[sentences[0][1]:sentences[0][2]] == sentences[0][0]
    assert text[sentences[1][1]:sentences[1][2]] == sentences[1][0]


def test_definitional_primary_span_extraction() -> None:
    """Isolates the defining sentence and symbol specification from narrative context."""
    text = (
        "Chemical kinetics is a branch of chemistry. "
        "Activation energy is defined as the minimum kinetic energy reactant molecules must possess. "
        "It is conventionally designated by the symbol Ea. "
        "Higher temperature increases reaction rate."
    )
    query = "What is activation energy and what is its symbol?"
    intent_result = detect_query_intent(query)

    spans = extract_answer_spans(text, query, intent_result)
    roles = [s.role for s in spans]
    assert "primary_definition" in roles
    assert "symbol_specification" in roles

    def_span = next(s for s in spans if s.role == "primary_definition")
    assert "is defined as the minimum kinetic energy" in def_span.text
    assert text[def_span.char_start:def_span.char_end] == def_span.text

    sym_span = next(s for s in spans if s.role == "symbol_specification")
    assert "designated by the symbol Ea" in sym_span.text
    assert text[sym_span.char_start:sym_span.char_end] == sym_span.text


def test_quantitative_calculation_step_extraction() -> None:
    """Isolates formula, numerical values, and calculation solution spans."""
    text = (
        "Consider temperature dependence in kinetics. "
        "The reaction follows the equation k = A * exp(-Ea/RT). "
        "Given: T = 300 K, A = 1.0e11, Ea = 50 kJ/mol. "
        "Solution: k = 2.4e-3 mol/L."
    )
    query = "Calculate rate constant k from temperature"
    intent_result = detect_query_intent(query)

    spans = extract_answer_spans(text, query, intent_result)
    roles = [s.role for s in spans]
    assert "formula_definition" in roles
    assert "numerical_values" in roles
    assert "calculation_solution" in roles

    sol_span = next(s for s in spans if s.role == "calculation_solution")
    assert "Solution: k = 2.4e-3 mol/L." in sol_span.text
    assert text[sol_span.char_start:sol_span.char_end] == sol_span.text


def test_procedural_step_span_extraction() -> None:
    """Extracts ordered step instructions with exact character offsets."""
    text = (
        "To determine activation energy in the laboratory: "
        "Step 1: Measure rate constants at multiple temperatures. "
        "Step 2: Plot ln(k) against 1/T. "
        "Step 3: Calculate activation energy from the slope."
    )
    query = "How to measure activation energy in lab"
    intent_result = detect_query_intent(query)

    spans = extract_answer_spans(text, query, intent_result)
    roles = [s.role for s in spans]
    assert roles.count("procedural_step") == 3
    assert all("Step" in s.text for s in spans)


def test_comparative_contrast_span_extraction() -> None:
    """Extracts explicit contrastive sentences in comparative queries."""
    text = (
        "Catalysts are categorized by phase. "
        "Homogeneous catalysts operate in the same phase as reactants, whereas heterogeneous catalysts operate in a distinct phase. "
        "Industrial plants often prefer heterogeneous catalysts."
    )
    query = "Compare homogeneous and heterogeneous catalysts"
    intent_result = detect_query_intent(query)

    spans = extract_answer_spans(text, query, intent_result)
    assert len(spans) >= 1
    assert any(s.role == "contrastive_statement" for s in spans)
    assert any("whereas" in s.text for s in spans)


def test_causal_mechanism_span_extraction() -> None:
    """Extracts causal mechanism explanation linking factors to outcome."""
    text = (
        "Temperature strongly affects chemical reactions. "
        "The reaction rate increases because higher temperature gives molecules greater kinetic energy, which causes more collisions to exceed the barrier. "
        "This effect is exponential."
    )
    query = "Why does reaction rate increase with temperature?"
    intent_result = detect_query_intent(query)

    spans = extract_answer_spans(text, query, intent_result)
    assert any(s.role == "causal_mechanism" for s in spans)


def test_overview_introductory_span_extraction() -> None:
    """Extracts high-level overview and introductory summary spans."""
    text = (
        "In this chapter, we provide an overview of cellular respiration. "
        "Glucose is oxidized to produce ATP through glycolysis and the citric acid cycle. "
        "In summary, energy is harvested efficiently."
    )
    query = "Explain cellular respiration overview"
    intent_result = detect_query_intent(query)

    spans = extract_answer_spans(text, query, intent_result)
    assert any(s.role == "overview_intro" for s in spans)


# ==============================================================================
# 2. CITATION RESOLUTION & CLUSTER SYNTHESIS TESTS
# ==============================================================================


@pytest.mark.django_db
def test_printed_page_resolution_using_document_page_map(
    db,
    library_a: Library,
    user_a: User,
) -> None:
    """Maps physical document page (e.g. 48) to printed textbook page label (e.g. '36')."""
    res = Resource.objects.create(
        library=library_a,
        name="General Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="chem_page.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem_page.pdf",
        checksum="hash-chem-page-s10",
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
    # Map physical page 48 -> printed "36"
    DocumentPageMap.objects.create(
        processing_run=run,
        resource=res,
        physical_page=48,
        printed_label="36",
    )

    chunk_id = uuid.uuid4()
    chunk_dto = SearchResultItemDTO(
        chunk_id=chunk_id,
        score=0.90,
        text="Sample textbook chunk.",
        provenance=ProvenanceDTO(
            resource_id=res.id,
            resource_name=res.name,
            library_id=library_a.id,
            library_name=library_a.name,
            page_start=48,
            page_end=48,
            section="Chapter 14: Chemical Kinetics",
            sequence=1,
            char_start=0,
            char_end=50,
            content_sha256="hash-p-48",
        ),
    )

    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    citations = resolve_chunk_citations([chunk_dto], scope)

    cit = citations[chunk_id]
    assert cit.printed_page == "36"
    assert cit.physical_page == 48
    assert cit.formatted == "General Chemistry, Chapter 14: Chemical Kinetics, p. 36"


@pytest.mark.django_db
def test_fallback_to_physical_page_when_no_page_map(
    db,
    library_a: Library,
    user_a: User,
) -> None:
    """When DocumentPageMap is not available, falls back safely to physical page number."""
    res = Resource.objects.create(
        library=library_a,
        name="Organic Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="org_chem.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/org_chem.pdf",
        checksum="hash-org-page-s10",
        status=ResourceStatus.READY,
        created_by=user_a,
    )

    chunk_id = uuid.uuid4()
    chunk_dto = SearchResultItemDTO(
        chunk_id=chunk_id,
        score=0.88,
        text="Sample organic text.",
        provenance=ProvenanceDTO(
            resource_id=res.id,
            resource_name=res.name,
            library_id=library_a.id,
            library_name=library_a.name,
            page_start=15,
            page_end=15,
            section="Chapter 3: Alkanes",
            sequence=1,
            char_start=0,
            char_end=50,
            content_sha256="hash-p-15",
        ),
    )

    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    citations = resolve_chunk_citations([chunk_dto], scope)

    cit = citations[chunk_id]
    assert cit.printed_page == "15"
    assert cit.physical_page == 15
    assert cit.formatted == "Organic Chemistry, Chapter 3: Alkanes, p. 15"


@pytest.mark.django_db
def test_multi_page_range_citation_formatting(
    db,
    library_a: Library,
    user_a: User,
) -> None:
    """Formats multi-page range as 'pp. 38–39'."""
    res = Resource.objects.create(
        library=library_a,
        name="Physical Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="phys_chem.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/phys_chem.pdf",
        checksum="hash-phys-page-s10",
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
    DocumentPageMap.objects.create(processing_run=run, resource=res, physical_page=50, printed_label="38")
    DocumentPageMap.objects.create(processing_run=run, resource=res, physical_page=51, printed_label="39")

    chunk_id = uuid.uuid4()
    chunk_dto = SearchResultItemDTO(
        chunk_id=chunk_id,
        score=0.91,
        text="Sample multi-page text.",
        provenance=ProvenanceDTO(
            resource_id=res.id,
            resource_name=res.name,
            library_id=library_a.id,
            library_name=library_a.name,
            page_start=50,
            page_end=51,
            section="Section 4.2",
            sequence=1,
            char_start=0,
            char_end=80,
            content_sha256="hash-p-50-51",
        ),
    )

    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    citations = resolve_chunk_citations([chunk_dto], scope)

    cit = citations[chunk_id]
    assert cit.printed_page == "38–39"
    assert cit.formatted == "Physical Chemistry, Section 4.2, pp. 38–39"


@pytest.mark.django_db
def test_multi_chunk_derivation_cluster_synthesis(
    db,
    library_a: Library,
    user_a: User,
) -> None:
    """Synthesizes consecutive calculation chunks into a unified derivation cluster."""
    res = Resource.objects.create(
        library=library_a,
        name="General Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="chem_deriv.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem_deriv.pdf",
        checksum="hash-chem-deriv-s10",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    c1 = SearchResultItemDTO(
        chunk_id=uuid.uuid4(),
        score=0.92,
        text="The two-point Arrhenius equation is k = A * exp(-Ea/RT).",
        provenance=ProvenanceDTO(
            resource_id=res.id,
            resource_name=res.name,
            library_id=library_a.id,
            library_name=library_a.name,
            page_start=40,
            page_end=40,
            section="Chapter 14: Kinetics",
            sequence=1,
            char_start=0,
            char_end=50,
            content_sha256="c1",
        ),
    )
    c2 = SearchResultItemDTO(
        chunk_id=uuid.uuid4(),
        score=0.87,
        text="Substitute experimental values: T1 = 300 K, T2 = 350 K, k1 = 0.02, k2 = 0.15.",
        provenance=ProvenanceDTO(
            resource_id=res.id,
            resource_name=res.name,
            library_id=library_a.id,
            library_name=library_a.name,
            page_start=40,
            page_end=40,
            section="Chapter 14: Kinetics",
            sequence=2,
            char_start=51,
            char_end=120,
            content_sha256="c2",
        ),
    )
    c3 = SearchResultItemDTO(
        chunk_id=uuid.uuid4(),
        score=0.85,
        text="Solution: Ea = 52.3 kJ/mol.",
        provenance=ProvenanceDTO(
            resource_id=res.id,
            resource_name=res.name,
            library_id=library_a.id,
            library_name=library_a.name,
            page_start=41,
            page_end=41,
            section="Chapter 14: Kinetics",
            sequence=3,
            char_start=121,
            char_end=150,
            content_sha256="c3",
        ),
    )

    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    citations = resolve_chunk_citations([c1, c2, c3], scope)

    cluster = synthesize_derivation_cluster(
        cluster_items=[c1, c2, c3],
        query_text="Calculate activation energy from experimental values",
        intent_result=QueryIntentResult(intent=QueryIntent.QUANTITATIVE, confidence=0.95, matched_cue="calculate"),
        citations_map=citations,
    )


    assert cluster is not None
    assert cluster.is_complete_derivation is True
    assert len(cluster.derivation_steps) >= 2
    assert "52.3 kJ/mol" in cluster.combined_text


# ==============================================================================
# 3. END-TO-END SECURITY & API RESPONSE TESTS
# ==============================================================================

@pytest.mark.django_db
def test_cross_library_citation_isolation(
    db,
    library_a: Library,
    library_b: Library,
    user_a: User,
) -> None:
    """User A in Library A cannot resolve or view page maps from Library B."""
    res_b = Resource.objects.create(
        library=library_b,
        name="Secret Chemistry B",
        resource_type=ResourceType.PDF,
        original_filename="secret_b.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_b/secret_b.pdf",
        checksum="hash-sec-b-s10",
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
        embedding_model="fake-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    DocumentPageMap.objects.create(
        processing_run=run_b,
        resource=res_b,
        physical_page=10,
        printed_label="Secret-99",
    )

    # Fake chunk referencing Library B
    chunk_b = SearchResultItemDTO(
        chunk_id=uuid.uuid4(),
        score=0.90,
        text="Secret text.",
        provenance=ProvenanceDTO(
            resource_id=res_b.id,
            resource_name=res_b.name,
            library_id=library_b.id,
            library_name=library_b.name,
            page_start=10,
            page_end=10,
            section="Secret",
            sequence=1,
            char_start=0,
            char_end=50,
            content_sha256="cb",
        ),
    )

    # Scope restricted only to Library A
    scope_a = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    citations = resolve_chunk_citations([chunk_b], scope_a)
    # Citation must fall back to physical page and NOT resolve Library B's "Secret-99"
    assert citations[chunk_b.chunk_id].printed_page != "Secret-99"
    assert citations[chunk_b.chunk_id].printed_page == "10"


@pytest.mark.django_db
def test_end_to_end_search_api_with_stage10_citation_and_spans(
    db,
    library_a: Library,
    user_a: User,
    membership_a: Membership,
    library_student_policy_a: LibraryAccessPolicy,
) -> None:
    """Verify additive citation and answer_spans in knowledge search API response."""
    provider = get_embedding_provider()
    res = Resource.objects.create(
        library=library_a,
        name="General Chemistry",
        resource_type=ResourceType.PDF,
        original_filename="chem_s10_api.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chem_s10.pdf",
        checksum="hash-chem-s10-api",
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
    DocumentPageMap.objects.create(
        processing_run=run,
        resource=res,
        physical_page=48,
        printed_label="36",
    )
    c = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=1,
        text="Activation energy is defined as the minimum kinetic energy reactant molecules must possess to react.",
        token_count=15,
        char_start=0,
        char_end=102,
        page_start=48,
        page_end=48,
        section="Chapter 14: Chemical Kinetics",
        content_sha256="hash-chunk-s10-api",
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

    assert data["result_count"] >= 1
    top_item = data["results"][0]

    # Verify Stage 10 additive citation
    assert "citation" in top_item
    assert top_item["citation"] is not None
    assert top_item["citation"]["printed_page"] == "36"
    assert top_item["citation"]["physical_page"] == 48
    assert "General Chemistry" in top_item["citation"]["formatted"]
    assert "p. 36" in top_item["citation"]["formatted"]

    # Verify Stage 10 additive answer spans
    assert "answer_spans" in top_item
    assert top_item["answer_spans"] is not None
    assert len(top_item["answer_spans"]) >= 1
    primary_span = top_item["answer_spans"][0]
    assert primary_span["role"] == "primary_definition"
    assert "is defined as the minimum kinetic energy" in primary_span["text"]

    # Verify 14-field provenance remains 100% intact
    prov = top_item["provenance"]
    assert prov["page_start"] == 48
    assert prov["resource_name"] == "General Chemistry"

    # Verify metadata
    assert data["metadata"]["citation_resolution_applied"] is True
