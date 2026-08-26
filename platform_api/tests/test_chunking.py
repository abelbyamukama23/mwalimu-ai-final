"""Tests for deterministic chunking engine, boundaries, overlap, and provenance."""

import hashlib
import math

from platform_api.apps.processing.chunker import (
    chunk,
)
from platform_api.apps.processing.extractors import ExtractedDocument, ExtractedPage
from platform_api.apps.processing.normalizer import (
    normalize,
)


def test_chunking_determinism() -> None:
    """Identical input yields identical chunk results."""
    text = (
        "Architecture Overview\n\n"
        "Mwalimu is a multi-tenant AI platform providing high-performance "
        "document indexing. " * 30
    )
    doc = normalize(
        ExtractedDocument(
            pages=[
                ExtractedPage(page=1, text=text, heading="Overview"),
            ]
        )
    )

    chunks1 = chunk(doc, target_size=1000, overlap=150)
    chunks2 = chunk(doc, target_size=1000, overlap=150)

    assert len(chunks1) > 1
    assert len(chunks1) == len(chunks2)

    for c1, c2 in zip(chunks1, chunks2, strict=True):
        assert c1.sequence == c2.sequence
        assert c1.text == c2.text
        assert c1.token_count == c2.token_count
        assert c1.char_start == c2.char_start
        assert c1.char_end == c2.char_end
        assert c1.page_start == c2.page_start
        assert c1.section == c2.section
        assert c1.content_sha256 == c2.content_sha256


def test_chunking_provenance_and_token_count() -> None:
    """Chunks maintain page numbers, nearest heading, and provenance."""
    doc = normalize(
        ExtractedDocument(
            pages=[
                ExtractedPage(
                    page=1,
                    text=(
                        "Introduction to Algorithms\n\n"
                        "Sorting and searching algorithms are fundamental."
                    ),
                    heading="Section 1",
                ),
                ExtractedPage(
                    page=2,
                    text=(
                        "Advanced Graphs\n\n"
                        "Graph traversal techniques include BFS and DFS."
                    ),
                    heading="Section 2",
                ),
            ]
        )
    )

    chunks = chunk(doc, target_size=2000, overlap=300)

    assert len(chunks) == 2
    c1, c2 = chunks[0], chunks[1]

    assert c1.sequence == 0
    assert c1.page_start == 1
    assert c1.page_end == 1
    assert c1.section == "Section 1"
    assert c1.token_count == math.ceil(len(c1.text) / 4)
    assert c1.content_sha256 == hashlib.sha256(c1.text.encode("utf-8")).hexdigest()

    assert c2.sequence == 1
    assert c2.page_start == 2
    assert c2.page_end == 2
    assert c2.section == "Section 2"


def test_chunking_splits_large_paragraph_by_sentences() -> None:
    """Paragraphs exceeding target size are split across sentence boundaries."""
    sent1 = "The first sentence describes introductory background information."
    sent2 = "The second sentence elaborates on theoretical foundations."
    sent3 = "The third sentence concludes the section with practical applications."
    para = f"{sent1} {sent2} {sent3}"

    doc = normalize(ExtractedDocument(pages=[ExtractedPage(page=1, text=para)]))

    # Set target size smaller than full paragraph but larger than single sentence
    target_size = len(sent1) + len(sent2) + 5
    chunks = chunk(doc, target_size=target_size, overlap=20)

    assert len(chunks) >= 2
    # First chunk contains sentence 1 and sentence 2
    assert sent1 in chunks[0].text


def test_chunking_empty_document() -> None:
    """Empty normalized document returns empty chunk list."""
    doc = normalize(ExtractedDocument(pages=[]))
    chunks = chunk(doc)
    assert chunks == []
