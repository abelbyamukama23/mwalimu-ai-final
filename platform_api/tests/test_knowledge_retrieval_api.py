"""Integration tests for Knowledge Retrieval Gateway API endpoint."""

import uuid

import pytest
from rest_framework.test import APIClient

from platform_api.apps.knowledge.authentication import mint_delegated_token
from platform_api.apps.libraries.models import (
    Library,
    LibraryAccessPolicy,
)
from platform_api.apps.memberships.models import Membership
from platform_api.apps.processing.chunker import ChunkResult
from platform_api.apps.processing.embedding.fake_provider import FakeEmbeddingProvider
from platform_api.apps.processing.indexing import (
    activate_run,
    write_chunks_and_embeddings,
)
from platform_api.apps.processing.models import ProcessingRun
from platform_api.apps.resources.models import Resource, ResourceStatus, ResourceType
from platform_api.apps.resources.object_key import generate_resource_object_key
from platform_api.apps.users.models import User


@pytest.fixture
def indexed_resource_lib_a(db, library_a: Library, user_a: User) -> Resource:
    """Create an indexed and active resource in Library A."""
    res_id = uuid.uuid4()
    resource = Resource.objects.create(
        id=res_id,
        library=library_a,
        name="Photosynthesis Textbook",
        resource_type=ResourceType.PDF,
        original_filename="photosynthesis.pdf",
        content_type="application/pdf",
        size=4096,
        object_key=generate_resource_object_key(library_a.pk, res_id),
        checksum="hash-photo-123",
        status=ResourceStatus.READY,
        created_by=user_a,
    )

    provider = FakeEmbeddingProvider(dimensions=1536)

    run = ProcessingRun.objects.create(
        resource=resource,
        library=library_a,
        source_checksum=resource.checksum,
        pipeline_version="1",
        extractor_version="pypdf-5",
        chunker_version="1",
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        embedding_dimensions=provider.dimensions,
    )

    chunks = [
        ChunkResult(
            sequence=0,
            text="Photosynthesis occurs in plant chloroplasts using sunlight.",
            token_count=8,
            char_start=0,
            char_end=58,
            page_start=12,
            page_end=12,
            section="Energy Production > Chloroplasts",
            content_sha256="sha-chunk-0",
        ),
        ChunkResult(
            sequence=1,
            text="Cellular respiration converts glucose into ATP in mitochondria.",
            token_count=8,
            char_start=60,
            char_end=123,
            page_start=13,
            page_end=13,
            section="Energy Production > Mitochondria",
            content_sha256="sha-chunk-1",
        ),
    ]

    vectors = provider.embed_texts([c.text for c in chunks])
    write_chunks_and_embeddings(run, chunks, vectors)
    activate_run(run)

    return resource


@pytest.fixture
def indexed_resource_lib_b(db, library_b: Library, user_b: User) -> Resource:
    """Create an indexed and active resource in Library B (Institution B)."""
    res_id = uuid.uuid4()
    resource = Resource.objects.create(
        id=res_id,
        library=library_b,
        name="Organic Chemistry Guide",
        resource_type=ResourceType.PDF,
        original_filename="org_chem.pdf",
        content_type="application/pdf",
        size=4096,
        object_key=generate_resource_object_key(library_b.pk, res_id),
        checksum="hash-chem-123",
        status=ResourceStatus.READY,
        created_by=user_b,
    )

    provider = FakeEmbeddingProvider(dimensions=1536)

    run = ProcessingRun.objects.create(
        resource=resource,
        library=library_b,
        source_checksum=resource.checksum,
        pipeline_version="1",
        extractor_version="pypdf-5",
        chunker_version="1",
        embedding_model=provider.model_id,
        embedding_version=provider.embedding_version,
        embedding_dimensions=provider.dimensions,
    )

    chunks = [
        ChunkResult(
            sequence=0,
            text="Hydrocarbons and covalent bonding in organic compounds.",
            token_count=7,
            char_start=0,
            char_end=55,
            page_start=5,
            page_end=5,
            section="Hydrocarbons",
            content_sha256="sha-chunk-b0",
        )
    ]

    vectors = provider.embed_texts([c.text for c in chunks])
    write_chunks_and_embeddings(run, chunks, vectors)
    activate_run(run)

    return resource


@pytest.mark.django_db
def test_search_unauthenticated_returns_401(api_client: APIClient) -> None:
    """Unauthenticated request returns 401 Unauthorized."""
    response = api_client.post(
        "/api/v1/knowledge/search/",
        {"query": "photosynthesis"},
        format="json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_search_with_user_jwt_and_14_field_provenance(
    client_a: APIClient,
    user_a: User,
    membership_a: Membership,
    library_student_policy_a: LibraryAccessPolicy,
    indexed_resource_lib_a: Resource,
) -> None:
    """Authorized search returns results with 14-field evidence contract."""
    response = client_a.post(
        "/api/v1/knowledge/search/",
        {
            "query": "sunlight chloroplasts in plants",
            "top_k": 5,
        },
        format="json",
    )

    assert response.status_code == 200
    data = response.data

    assert data["query"] == "sunlight chloroplasts in plants"
    assert data["result_count"] >= 1
    assert data["embedding_model"] == "text-embedding-3-small"
    assert data["embedding_version"] == "1"

    result = data["results"][0]
    assert "chunk_id" in result
    assert "score" in result
    assert "text" in result
    assert "chloroplasts" in result["text"]

    # Verify all 14 provenance fields
    prov = result["provenance"]
    assert prov["resource_id"] == str(indexed_resource_lib_a.id)
    assert prov["resource_name"] == "Photosynthesis Textbook"
    assert prov["library_id"] == str(indexed_resource_lib_a.library.id)
    assert prov["library_name"] == "Library A"
    assert prov["page_start"] == 12
    assert prov["page_end"] == 12
    assert prov["section"] == "Energy Production > Chloroplasts"
    assert prov["sequence"] == 0
    assert prov["char_start"] == 0
    assert prov["char_end"] == 58
    assert prov["content_sha256"] == "sha-chunk-0"

    assert data["metadata"]["libraries_searched"] == 1
    assert data["metadata"]["embedding_dimensions"] == 1536
    assert data["metadata"]["search_time_ms"] >= 0


@pytest.mark.django_db
def test_search_with_delegated_execution_token(
    api_client: APIClient,
    user_a: User,
    membership_a: Membership,
    library_student_policy_a: LibraryAccessPolicy,
    indexed_resource_lib_a: Resource,
) -> None:
    """Agent Service with Delegated Execution Token searches on behalf of user."""
    agent_run_id = uuid.uuid4()
    session_id = uuid.uuid4()

    token = mint_delegated_token(
        user_id=user_a.id,
        agent_run_id=agent_run_id,
        session_id=session_id,
    )

    response = api_client.post(
        "/api/v1/knowledge/search/",
        {"query": "photosynthesis in plants"},
        HTTP_AUTHORIZATION=f"Bearer {token}",
        format="json",
    )

    assert response.status_code == 200
    assert response.data["result_count"] >= 1
    assert response.data["results"][0]["provenance"]["library_name"] == "Library A"


@pytest.mark.django_db
def test_cross_institution_isolation(
    client_a: APIClient,
    user_a: User,
    membership_a: Membership,
    library_student_policy_a: LibraryAccessPolicy,
    indexed_resource_lib_a: Resource,
    indexed_resource_lib_b: Resource,
) -> None:
    """User A from Institution A can never retrieve chunks from Institution B."""
    response = client_a.post(
        "/api/v1/knowledge/search/",
        {
            "query": "covalent bonding in organic compounds",
            "top_k": 10,
        },
        format="json",
    )

    assert response.status_code == 200
    # Chunks from Library B (Organic Chemistry) must NOT be present
    for item in response.data["results"]:
        assert item["provenance"]["library_id"] != str(
            indexed_resource_lib_b.library.id
        )
        assert item["provenance"]["resource_id"] != str(indexed_resource_lib_b.id)


@pytest.mark.django_db
def test_discoverable_library_without_policy_returns_zero_results(
    client_a: APIClient,
    user_a: User,
    membership_a: Membership,
    discoverable_library_a: Library,
) -> None:
    """Discoverable library without explicit access policy yields 0 results (Rule B)."""
    response = client_a.post(
        "/api/v1/knowledge/search/",
        {
            "query": "test query",
            "library_ids": [str(discoverable_library_a.id)],
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["result_count"] == 0
    assert response.data["results"] == []


@pytest.mark.django_db
def test_include_text_false_omits_chunk_text(
    client_a: APIClient,
    user_a: User,
    membership_a: Membership,
    library_student_policy_a: LibraryAccessPolicy,
    indexed_resource_lib_a: Resource,
) -> None:
    """When include_text=False, chunk text is returned as empty string."""
    response = client_a.post(
        "/api/v1/knowledge/search/",
        {
            "query": "photosynthesis",
            "include_text": False,
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["result_count"] >= 1
    assert response.data["results"][0]["text"] == ""
    assert (
        response.data["results"][0]["provenance"]["resource_name"]
        == "Photosynthesis Textbook"
    )


@pytest.mark.django_db
def test_request_validation_errors(client_a: APIClient) -> None:
    """Malformed requests return 400 Bad Request."""
    # 1. Missing query
    res1 = client_a.post("/api/v1/knowledge/search/", {}, format="json")
    assert res1.status_code == 400
    assert "query" in res1.data

    # 2. Blank / whitespace only query
    res2 = client_a.post("/api/v1/knowledge/search/", {"query": "   "}, format="json")
    assert res2.status_code == 400

    # 3. Invalid UUID in library_ids
    res3 = client_a.post(
        "/api/v1/knowledge/search/",
        {"query": "valid query", "library_ids": ["not-a-uuid"]},
        format="json",
    )
    assert res3.status_code == 400
