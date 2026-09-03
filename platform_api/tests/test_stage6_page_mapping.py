"""Tests for Stage 6: Printed-to-Physical Page Mapping & Retrieval Hardening."""

from __future__ import annotations

import io
import uuid
from collections.abc import Sequence

import pypdf
import pytest
from rest_framework.test import APIClient

from platform_api.apps.knowledge.authentication import mint_delegated_token

from platform_api.apps.knowledge.context_expansion import expand_retrieval_context
from platform_api.apps.knowledge.dto import ProvenanceDTO, SearchResultItemDTO
from platform_api.apps.knowledge.index_search import (
    find_candidate_index_pages,
    resolve_printed_page_labels_to_physical,
)
from platform_api.apps.knowledge.policies import EffectiveRetrievalScope
from platform_api.apps.libraries.models import Library, LibraryAccessPolicy
from platform_api.apps.memberships.models import Membership
from platform_api.apps.processing.embedding import get_embedding_provider
from platform_api.apps.processing.extractors import ExtractedPage, OutlineNode
from platform_api.apps.processing.extractors.pdf import extract_pdf
from platform_api.apps.processing.index_parser import (
    parse_index_entries,
    parse_page_references,
    parse_page_references_to_labels,
    resolve_page_labels_to_physical,
)
from platform_api.apps.processing.indexing import activate_run, write_chunks_and_embeddings
from platform_api.apps.processing.models import (
    BookIndexEntry,
    ChunkEmbedding,
    DocumentChunk,
    DocumentPageMap,
    DocumentStructureNode,
    PageLabelSource,
    ProcessingRun,
    ProcessingStatus,
)
from platform_api.apps.resources.models import Resource, ResourceStatus, ResourceType
from platform_api.apps.users.models import User


# ==============================================================================
# 1. ARABIC PRINTED PAGES MAPPED TO PHYSICAL PAGES
# ==============================================================================

def test_arabic_printed_pages_mapped_to_physical() -> None:
    """Printed page '1' in body maps to physical PDF page 12 due to 11 pages of front matter."""
    page_map = {"1": 12, "2": 13, "3": 14, "25": 36}
    assert resolve_page_labels_to_physical(["1", "25"], page_map) == [12, 36]


# ==============================================================================
# 2. ROMAN NUMERAL FRONT MATTER
# ==============================================================================

def test_roman_numeral_front_matter() -> None:
    """Roman numerals (e.g. 'ii', 'iv') map to front-matter pages and do NOT collide with Arabic numbers."""
    page_map = {
        "cover": 1,
        "ii": 2,
        "iii": 3,
        "iv": 4,
        "v": 5,
        "1": 6,
        "2": 7,
    }
    # Printed 'ii' is physical 2 (preface)
    assert resolve_page_labels_to_physical(["ii"], page_map) == [2]
    # Printed '2' is physical 7 (Chapter 1)
    assert resolve_page_labels_to_physical(["2"], page_map) == [7]
    # They do NOT collide
    assert resolve_page_labels_to_physical(["ii"], page_map) != resolve_page_labels_to_physical(["2"], page_map)


# ==============================================================================
# 3. BODY PAGE 1 BEGINNING AFTER FRONT MATTER
# ==============================================================================

def test_body_page_1_beginning_after_front_matter() -> None:
    """Body page 1 starts after front matter: printed labels preserve explicit distinction."""
    labels = ["i", "ii", "iii", "1", "2"]
    page_map = {lbl: idx + 1 for idx, lbl in enumerate(labels)}
    # '1' is physical 4, 'i' is physical 1
    assert resolve_page_labels_to_physical(["1"], page_map) == [4]
    assert resolve_page_labels_to_physical(["i"], page_map) == [1]


# ==============================================================================
# 4. PDF /PageLabels EXTRACTION
# ==============================================================================

def test_pdf_pagelabels_extraction() -> None:
    """pypdf correctly extracts author-declared /PageLabels in the PDF catalog."""
    writer = pypdf.PdfWriter()
    for _ in range(5):
        writer.add_blank_page(width=100, height=100)

    # Pages 0..1: roman lower ('i', 'ii')
    writer.set_page_label(0, 1, style="/r")
    # Pages 2..4: decimal arabic starting at 1 ('1', '2', '3')
    writer.set_page_label(2, 4, style="/D", start=1)

    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)

    doc = extract_pdf(buf.getvalue())
    assert len(doc.page_labels) == 5
    assert doc.page_labels[0] == (1, "i", "native")
    assert doc.page_labels[1] == (2, "ii", "native")
    assert doc.page_labels[2] == (3, "1", "native")
    assert doc.page_labels[3] == (4, "2", "native")
    assert doc.page_labels[4] == (5, "3", "native")


# ==============================================================================
# 5. INDEX REFERENCE RESOLVED THROUGH PAGE MAP
# ==============================================================================

def test_index_reference_resolved_through_page_map() -> None:
    """Index entry 'activation energy, 6, 27' resolves through page map to physical pages 17 and 38."""
    page = ExtractedPage(
        page=100,
        text="SUBJECT INDEX\nactivation energy ........ 6, 27\n",
    )
    # Page map has offset +11 (front matter of 11 pages)
    page_map = {"6": 17, "27": 38}
    entries = parse_index_entries([page], page_map=page_map)

    assert len(entries) == 1
    assert entries[0].term == "activation energy"
    assert entries[0].raw_page_references == "6, 27"
    assert entries[0].target_physical_pages == [17, 38]


# ==============================================================================
# 6. INDEX REFERENCE WITH UNRESOLVED PAGE NEVER FABRICATES
# ==============================================================================

def test_index_reference_with_unresolved_page_never_fabricates() -> None:
    """If index references '7, 27, 103' and 103 is not in page map, 103 is omitted and NOT fabricated."""
    page = ExtractedPage(
        page=50,
        text="SUBJECT INDEX\nactivation energy ........ 7, 27, 103\n",
    )
    # 103 is beyond the document or unmapped
    page_map = {"7": 18, "27": 38}
    entries = parse_index_entries([page], page_map=page_map)

    assert len(entries) == 1
    assert entries[0].target_physical_pages == [18, 38]
    assert 103 not in entries[0].target_physical_pages


# ==============================================================================
# 7. MULTIPLE INDEX REFERENCES
# ==============================================================================

def test_multiple_index_references_with_page_map() -> None:
    """Multiple entries each resolve their respective printed page references via page map."""
    page = ExtractedPage(
        page=50,
        text="""SUBJECT INDEX
chemical kinetics, 4, 5, 6
reaction rates, 7, 8
""",
    )
    page_map = {"4": 15, "5": 16, "6": 17, "7": 18, "8": 19}
    entries = parse_index_entries([page], page_map=page_map)

    assert len(entries) == 2
    assert entries[0].target_physical_pages == [15, 16, 17]
    assert entries[1].target_physical_pages == [18, 19]


# ==============================================================================
# 8. PRINTED PAGE RANGE RESOLVED THROUGH PAGE MAP
# ==============================================================================

def test_printed_page_range_resolved_through_page_map() -> None:
    """Printed range '42–45' resolves to physical pages 53, 54, 55, 56."""
    page = ExtractedPage(
        page=50,
        text="SUBJECT INDEX\nchemical equilibrium ..... 42–45\n",
    )
    page_map = {"42": 53, "43": 54, "44": 55, "45": 56}
    entries = parse_index_entries([page], page_map=page_map)

    assert len(entries) == 1
    assert entries[0].target_physical_pages == [53, 54, 55, 56]


# ==============================================================================
# 9. INDEX + TOC + PAGE-MAP COMPLETE INTERSECTION RETRIEVAL
# ==============================================================================

@pytest.mark.django_db
def test_index_toc_pagemap_complete_intersection(
    db,
    library_a: Library,
    user_a: User,
    membership_a: Membership,
    library_student_policy_a: LibraryAccessPolicy,
) -> None:
    """TOC section (Kinetics physical 15-25) intersects index 'reaction rate' (printed 7 -> physical 18)."""
    res = Resource.objects.create(
        library=library_a,
        name="chemistry_pagemap.pdf",
        resource_type=ResourceType.PDF,
        original_filename="chemistry_pagemap.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/chemistry_pagemap.pdf",
        checksum="hash-chem-pmap",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    provider = get_embedding_provider()
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

    # DocumentPageMap: printed 7 -> physical 18, printed 81 -> physical 92
    DocumentPageMap.objects.create(
        processing_run=run,
        resource=res,
        physical_page=18,
        printed_label="7",
        normalized_label="7",
        source=PageLabelSource.NATIVE,
    )
    DocumentPageMap.objects.create(
        processing_run=run,
        resource=res,
        physical_page=92,
        printed_label="81",
        normalized_label="81",
        source=PageLabelSource.NATIVE,
    )

    # TOC Section 1: Chemical Kinetics (physical pages 15-25)
    node_kinetics = DocumentStructureNode.objects.create(
        processing_run=run,
        resource=res,
        library=library_a,
        title="Chapter 1: Chemical Kinetics",
        normalized_title="chapter 1: chemical kinetics",
        level=1,
        page_start=15,
        page_end=25,
        sequence=0,
    )
    # TOC Section 2: Thermodynamics (physical pages 85-100)
    node_thermo = DocumentStructureNode.objects.create(
        processing_run=run,
        resource=res,
        library=library_a,
        title="Chapter 8: Thermodynamics",
        normalized_title="chapter 8: thermodynamics",
        level=1,
        page_start=85,
        page_end=100,
        sequence=1,
    )

    # Chunk in kinetics on physical page 18 (printed page 7)
    c_kin = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=1,
        text="The rate of a chemical reaction is proportional to temperature and activation collision frequency.",
        token_count=15,
        char_start=0,
        char_end=100,
        page_start=18,
        page_end=18,
        structure_node=node_kinetics,
        section="Chapter 1: Chemical Kinetics",
        content_sha256="hash-kin-18",
    )
    ChunkEmbedding.objects.create(
        chunk=c_kin,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    # Chunk in thermo on physical page 92 (printed page 81)
    c_thm = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=2,
        text="Thermodynamics measures heat and temperature equilibrium without consideration of reaction rate.",
        token_count=13,
        char_start=100,
        char_end=200,
        page_start=92,
        page_end=92,
        structure_node=node_thermo,
        section="Chapter 8: Thermodynamics",
        content_sha256="hash-thm-92",
    )
    ChunkEmbedding.objects.create(
        chunk=c_thm,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    # BookIndexEntry pointing to resolved physical page 18
    BookIndexEntry.objects.create(
        processing_run=run,
        resource=res,
        term="reaction rate",
        normalized_term="reaction rate",
        raw_page_references="7",
        target_physical_pages=[18],
    )
    BookIndexEntry.objects.create(
        processing_run=run,
        resource=res,
        term="temperature",
        normalized_term="temperature",
        raw_page_references="7, 81",
        target_physical_pages=[18, 92],
    )

    client = APIClient()
    token = mint_delegated_token(user_id=user_a.pk)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    response = client.post(
        "/api/v1/knowledge/search/",
        {
            "query": "How does temperature affect reaction rate?",
            "top_k": 3,
        },
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["result_count"] > 0
    assert data["metadata"]["retrieval_strategy"] == "index_guided_hybrid"
    top = data["results"][0]
    assert top["provenance"]["page_start"] == 18
    assert "activation collision" in top["text"]


# ==============================================================================
# 10. INDEX WITHOUT PAGE MAP FALLBACK
# ==============================================================================

@pytest.mark.django_db
def test_index_without_page_map_fallback(db, library_a: Library, user_a: User) -> None:
    """Document without DocumentPageMap falls back gracefully to raw integer page references."""
    res = Resource.objects.create(
        library=library_a,
        name="no_map.pdf",
        resource_type=ResourceType.PDF,
        original_filename="no_map.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/no_map.pdf",
        checksum="hash-no-map",
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
    BookIndexEntry.objects.create(
        processing_run=run,
        resource=res,
        term="catalyst",
        normalized_term="catalyst",
        raw_page_references="15",
        target_physical_pages=[15],
    )

    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    pages = find_candidate_index_pages("catalyst", scope)
    assert pages == [15]


# ==============================================================================
# 11. DOCUMENT WITHOUT INDEX FALLBACK
# ==============================================================================

@pytest.mark.django_db
def test_document_without_index_fallback(db, library_a: Library) -> None:
    """Document with no index records returns empty candidate pages without error."""
    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    pages = find_candidate_index_pages("quantum entanglement", scope)
    assert pages == []


# ==============================================================================
# 12. DOCUMENT WITHOUT STRUCTURE FALLBACK
# ==============================================================================

@pytest.mark.django_db
def test_document_without_structure_fallback(
    db, library_a: Library, user_a: User
) -> None:
    """Retriever functions seamlessly when no structure nodes exist."""
    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    resolved = resolve_printed_page_labels_to_physical(uuid.uuid4(), ["1"], scope)
    assert resolved == []


# ==============================================================================
# 13. CROSS-LIBRARY ISOLATION
# ==============================================================================

@pytest.mark.django_db
def test_cross_library_pagemap_isolation(
    db, library_a: Library, library_b: Library, user_a: User, user_b: User
) -> None:
    """Institution B cannot resolve printed pages for Institution A's resources."""
    res_a = Resource.objects.create(
        library=library_a,
        name="private_a.pdf",
        resource_type=ResourceType.PDF,
        original_filename="private_a.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/private_a.pdf",
        checksum="hash-iso-a",
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
        embedding_model="fake-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
        is_active=True,
    )
    DocumentPageMap.objects.create(
        processing_run=run_a,
        resource=res_a,
        physical_page=42,
        printed_label="1",
        normalized_label="1",
        source=PageLabelSource.NATIVE,
    )

    # Scope only authorizes Library B
    scope_b = EffectiveRetrievalScope(frozenset([library_b.id]), None)
    resolved = resolve_printed_page_labels_to_physical(res_a.id, ["1"], scope_b)

    # Zero leakage: returns empty
    assert resolved == []


# ==============================================================================
# 14. REPROCESSING REMOVES/REPLACES STALE PAGE MAPPINGS
# ==============================================================================

@pytest.mark.django_db
def test_reprocessing_removes_and_replaces_stale_page_mappings(
    db, library_a: Library, user_a: User
) -> None:
    """Reprocessing a resource replaces old DocumentPageMap records transactionally."""
    res = Resource.objects.create(
        library=library_a,
        name="reprocess_map.pdf",
        resource_type=ResourceType.PDF,
        original_filename="reprocess_map.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/reprocess_map.pdf",
        checksum="hash-rep-map-1",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    run1 = ProcessingRun.objects.create(
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

    # Run 1: printed '1' -> physical 10
    write_chunks_and_embeddings(
        run=run1,
        chunks=[],
        vectors=[],
        page_labels=[(10, "1", "detected")],
    )
    activate_run(run1)

    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    assert resolve_printed_page_labels_to_physical(res.id, ["1"], scope) == [10]

    # Run 2: reprocessing with new layout: printed '1' -> physical 25
    run2 = ProcessingRun.objects.create(
        resource=res,
        library=library_a,
        source_checksum="hash-rep-map-2",
        pipeline_version="1",
        extractor_version="1",
        chunker_version="1",
        embedding_model="fake-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.PROCESSING,
        is_active=False,
    )
    write_chunks_and_embeddings(
        run=run2,
        chunks=[],
        vectors=[],
        page_labels=[(25, "1", "detected")],
    )
    activate_run(run2)

    # Now Run 1 is deactivated and Run 2 is active: returns [25], old [10] is gone
    assert resolve_printed_page_labels_to_physical(res.id, ["1"], scope) == [25]


# ==============================================================================
# 15. WRONG GENERIC INDEX TERM DOES NOT OVERRIDE STRONGER EVIDENCE
# ==============================================================================

@pytest.mark.django_db
def test_wrong_generic_index_term_does_not_override_stronger_evidence(
    db,
    library_a: Library,
    user_a: User,
    membership_a: Membership,
    library_student_policy_a: LibraryAccessPolicy,
) -> None:
    """When an index term is generic, strong lexical + structural matching keeps core section top."""
    res = Resource.objects.create(
        library=library_a,
        name="bio.pdf",
        resource_type=ResourceType.PDF,
        original_filename="bio.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/bio.pdf",
        checksum="hash-bio",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    provider = get_embedding_provider()
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

    node_photo = DocumentStructureNode.objects.create(
        processing_run=run,
        resource=res,
        library=library_a,
        title="Chapter 4: Photosynthesis and Chloroplasts",
        normalized_title="chapter 4: photosynthesis and chloroplasts",
        level=1,
        page_start=40,
        page_end=55,
        sequence=0,
    )

    c_photo = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=1,
        text="Photosynthesis converts light energy into chemical energy within chloroplast thylakoids.",
        token_count=12,
        char_start=0,
        char_end=100,
        page_start=42,
        page_end=42,
        structure_node=node_photo,
        section="Chapter 4: Photosynthesis and Chloroplasts",
        content_sha256="hash-photo-42",
    )
    ChunkEmbedding.objects.create(
        chunk=c_photo,
        vector=[0.0] * provider.dimensions,
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        dimensions=provider.dimensions,
    )

    client = APIClient()
    token = mint_delegated_token(user_id=user_a.pk)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    response = client.post(
        "/api/v1/knowledge/search/",
        {
            "query": "Photosynthesis in chloroplast thylakoids",
            "top_k": 3,
        },
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["result_count"] > 0
    top = data["results"][0]
    assert "thylakoids" in top["text"]
    assert top["provenance"]["page_start"] == 42


# ==============================================================================
# 16. CONTEXT EXPANSION STILL OPERATES AFTER PAGE MAPPING
# ==============================================================================

@pytest.mark.django_db
def test_context_expansion_still_operates_after_page_mapping(
    db, library_a: Library, user_a: User
) -> None:
    """Context expansion expands sequence +- 1 around a retrieved chunk on physical page 18."""
    res = Resource.objects.create(
        library=library_a,
        name="expand_map.pdf",
        resource_type=ResourceType.PDF,
        original_filename="expand_map.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="lib_a/expand_map.pdf",
        checksum="hash-exp-map",
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
        title="Chapter 1",
        normalized_title="chapter 1",
        level=1,
        page_start=15,
        page_end=20,
        sequence=0,
    )

    c10 = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=10,
        text="Previous chunk on physical page 17.",
        token_count=6,
        char_start=0,
        char_end=50,
        page_start=17,
        page_end=17,
        structure_node=node,
        section="Chapter 1",
        content_sha256="hash-10",
    )
    c11 = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=11,
        text="Core retrieved chunk on physical page 18.",
        token_count=7,
        char_start=50,
        char_end=100,
        page_start=18,
        page_end=18,
        structure_node=node,
        section="Chapter 1",
        content_sha256="hash-11",
    )
    c12 = DocumentChunk.objects.create(
        processing_run=run,
        library=library_a,
        resource=res,
        sequence=12,
        text="Next chunk on physical page 19.",
        token_count=6,
        char_start=100,
        char_end=150,
        page_start=19,
        page_end=19,
        structure_node=node,
        section="Chapter 1",
        content_sha256="hash-12",
    )

    core_dto = SearchResultItemDTO(
        chunk_id=c11.id,
        score=0.95,
        text=c11.text,
        provenance=ProvenanceDTO(
            resource_id=res.id,
            resource_name=res.name,
            library_id=library_a.id,
            library_name=library_a.name,
            page_start=18,
            page_end=18,
            section="Chapter 1",
            sequence=11,
            char_start=50,
            char_end=100,
            content_sha256="hash-11",
        ),
    )

    scope = EffectiveRetrievalScope(frozenset([library_a.id]), None)
    expanded = expand_retrieval_context([core_dto], scope, context_window=1)

    assert len(expanded) == 3
    assert expanded[0].chunk_id == c11.id
    assert {x.chunk_id for x in expanded} == {c10.id, c11.id, c12.id}
    assert {x.provenance.sequence for x in expanded} == {10, 11, 12}

