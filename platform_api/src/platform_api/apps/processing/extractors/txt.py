"""Plain-text extractor using Python standard library."""

from __future__ import annotations

from . import ExtractedDocument, ExtractedPage, ExtractionError

EXTRACTOR_VERSION_TXT = "stdlib-1"


def extract_txt(content: bytes) -> ExtractedDocument:
    """Extract paragraphs from UTF-8 plain-text bytes.

    Args:
        content: Raw text bytes.

    Returns:
        ExtractedDocument containing paragraphs.

    Raises:
        ExtractionError: If content cannot be decoded as UTF-8.
    """
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExtractionError(f"Failed to decode text as UTF-8: {exc}") from exc

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs and text.strip():
        paragraphs = [text.strip()]

    pages = [
        ExtractedPage(
            page=None,
            text=paragraph,
            heading=None,
        )
        for paragraph in paragraphs
    ]

    return ExtractedDocument(pages=pages)
