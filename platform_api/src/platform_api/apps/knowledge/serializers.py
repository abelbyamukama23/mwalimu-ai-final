"""DRF serializers for Knowledge Gateway request validation and response formatting."""

from __future__ import annotations

from rest_framework import serializers

from .dto import SearchRequestDTO


class SearchRequestSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Serializer for validating search request payloads."""

    query = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=10000,
        trim_whitespace=True,
    )
    library_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_null=True,
        default=None,
    )
    resource_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_null=True,
        default=None,
    )
    top_k = serializers.IntegerField(
        required=False,
        default=10,
        min_value=1,
        max_value=50,
    )
    similarity_threshold = serializers.FloatField(
        required=False,
        allow_null=True,
        default=None,
        min_value=0.0,
        max_value=1.0,
    )
    include_text = serializers.BooleanField(
        required=False,
        default=True,
    )

    def validate_query(self, value: str) -> str:
        """Validate query text."""
        cleaned = value.replace("\x00", "").strip()
        if not cleaned:
            raise serializers.ValidationError(
                "Query text cannot be empty or whitespace only."
            )
        return cleaned

    def to_dto(self) -> SearchRequestDTO:
        """Convert validated serializer data to SearchRequestDTO."""
        data = self.validated_data
        return SearchRequestDTO(
            query=data["query"],
            library_ids=data.get("library_ids"),
            resource_ids=data.get("resource_ids"),
            top_k=data.get("top_k", 10),
            similarity_threshold=data.get("similarity_threshold"),
            include_text=data.get("include_text", True),
        )


class ProvenanceSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Serializer for 14-field citation provenance metadata."""

    resource_id = serializers.UUIDField()
    resource_name = serializers.CharField()
    library_id = serializers.UUIDField()
    library_name = serializers.CharField()
    page_start = serializers.IntegerField(allow_null=True)
    page_end = serializers.IntegerField(allow_null=True)
    section = serializers.CharField(allow_null=True)
    sequence = serializers.IntegerField()
    char_start = serializers.IntegerField()
    char_end = serializers.IntegerField()
    content_sha256 = serializers.CharField()


class SearchResultItemSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Serializer for a single scored chunk result."""

    chunk_id = serializers.UUIDField()
    score = serializers.FloatField()
    text = serializers.CharField()
    provenance = ProvenanceSerializer()


class SearchResponseSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Serializer for the top-level search response."""

    query = serializers.CharField()
    result_count = serializers.IntegerField()
    embedding_model = serializers.CharField()
    embedding_version = serializers.CharField()
    results = SearchResultItemSerializer(many=True)
    metadata = serializers.DictField()
