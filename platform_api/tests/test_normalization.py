"""Tests for the text normalization engine and provenance tracking."""

from platform_api.apps.processing.extractors import ExtractedDocument, ExtractedPage
from platform_api.apps.processing.normalizer import (
    normalize,
)


def test_normalize_whitespace_and_unicode() -> None:
    """Normalization cleans control chars, applies NFC, and collapses spaces."""
    doc = ExtractedDocument(
        pages=[
            ExtractedPage(
                page=1,
                text=(
                    "Caf\u0065\u0301\t \tand   restaurants.\n\n\n\n"
                    "Next  paragraph with   spaces."
                ),
                heading="Dining",
            )
        ]
    )

    norm = normalize(doc)

    assert not norm.is_empty
    assert "Café and restaurants." in norm.full_text
    assert "\n\n\n" not in norm.full_text
    assert len(norm.segments) == 1
    assert norm.segments[0].heading == "Dining"
    assert norm.segments[0].page == 1


def test_normalize_line_end_hyphenation() -> None:
    """Hyphenated words split across lines are joined properly."""
    doc = ExtractedDocument(
        pages=[
            ExtractedPage(
                page=1,
                text="The docu-\nment processing pipeline ensures reli-\nability.",
            )
        ]
    )

    norm = normalize(doc)

    assert "document" in norm.full_text
    assert "reliability" in norm.full_text
    assert "docu-\nment" not in norm.full_text


def test_normalize_repeated_header_footer_deduplication() -> None:
    """Headers and footers repeated across 3+ consecutive pages are stripped."""
    doc = ExtractedDocument(
        pages=[
            ExtractedPage(
                page=1, text="CONFIDENTIAL HEADER\nPage 1 content.\nPage 1 Footer"
            ),
            ExtractedPage(
                page=2, text="CONFIDENTIAL HEADER\nPage 2 content.\nPage 1 Footer"
            ),
            ExtractedPage(
                page=3, text="CONFIDENTIAL HEADER\nPage 3 content.\nPage 1 Footer"
            ),
        ]
    )

    norm = normalize(doc)

    assert "CONFIDENTIAL HEADER" not in norm.full_text
    assert "Page 1 Footer" not in norm.full_text
    assert "Page 1 content." in norm.full_text
    assert "Page 2 content." in norm.full_text
    assert "Page 3 content." in norm.full_text


def test_normalize_character_offsets() -> None:
    """Normalized segments retain character offsets relative to full_text."""
    doc = ExtractedDocument(
        pages=[
            ExtractedPage(page=1, text="First page content."),
            ExtractedPage(page=2, text="Second page content."),
        ]
    )

    norm = normalize(doc)

    assert len(norm.segments) == 2
    seg1 = norm.segments[0]
    seg2 = norm.segments[1]

    assert norm.full_text[seg1.char_start : seg1.char_end] == seg1.text
    assert norm.full_text[seg2.char_start : seg2.char_end] == seg2.text
    assert seg1.page == 1
    assert seg2.page == 2
