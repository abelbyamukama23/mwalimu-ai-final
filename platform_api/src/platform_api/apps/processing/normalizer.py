"""Text normalization engine for extracted document content.

Converts extracted pages into canonical, clean text while strictly preserving
structural provenance (page boundaries, headings, character offsets).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .extractors import ExtractedDocument, OutlineNode


@dataclass(frozen=True)
class NormalizedSegment:
    """A clean text segment retaining page and heading provenance."""

    text: str
    page: int | None
    heading: str | None
    char_start: int
    char_end: int


@dataclass(frozen=True)
class NormalizedDocument:
    """Canonical normalized document with ordered segments and assembled full text."""

    segments: list[NormalizedSegment] = field(default_factory=list)
    full_text: str = ""
    outline: list[OutlineNode] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if no usable normalized text exists."""
        return not bool(self.full_text.strip())



def _clean_unicode_and_controls(text: str) -> str:
    """Normalize to Unicode NFC and remove non-printable control characters."""
    normalized = unicodedata.normalize("NFC", text)
    # Preserve \n, \t, \r, remove all other control characters (categories C*)
    cleaned = "".join(
        char
        for char in normalized
        if char in ("\n", "\t", "\r") or not unicodedata.category(char).startswith("C")
    )
    return cleaned


def _clean_whitespace_and_hyphenation(text: str) -> str:
    """Clean newlines, fix line-end hyphenation, and collapse multiple spaces."""
    # Standardize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Fix line-end hyphenation (e.g. "connec-\ntion" -> "connection")
    text = re.sub(r"(\b[A-Za-z0-9]+)-\n([A-Za-z0-9]+\b)", r"\1\2", text)

    # Trim lines and collapse horizontal spaces
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)

    # Collapse 3 or more blank lines to a single paragraph break (\n\n)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _deduplicate_headers_footers(pages_text: list[str]) -> list[str]:
    """Remove header/footer lines repeated on >= 3 consecutive pages."""
    if len(pages_text) < 3:
        return pages_text

    # Extract first and last non-empty lines per page
    first_lines = []
    last_lines = []
    for text in pages_text:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        first_lines.append(lines[0] if lines else "")
        last_lines.append(lines[-1] if lines else "")

    # Identify repeated headers across >= 3 consecutive pages
    repeated_headers: set[str] = set()
    repeated_footers: set[str] = set()

    for i in range(len(pages_text) - 2):
        if (
            first_lines[i]
            and first_lines[i] == first_lines[i + 1] == first_lines[i + 2]
        ):
            repeated_headers.add(first_lines[i])
        if last_lines[i] and last_lines[i] == last_lines[i + 1] == last_lines[i + 2]:
            repeated_footers.add(last_lines[i])

    cleaned_pages: list[str] = []
    for text in pages_text:
        lines = text.split("\n")
        filtered_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped in repeated_headers or stripped in repeated_footers:
                continue
            filtered_lines.append(line)
        cleaned_pages.append("\n".join(filtered_lines).strip())

    return cleaned_pages


def normalize(doc: ExtractedDocument) -> NormalizedDocument:
    """Normalize extracted document pages into canonical text segments with offsets.

    Args:
        doc: Raw ExtractedDocument from extractor.

    Returns:
        NormalizedDocument with canonical text and exact character ranges.
    """
    if not doc.pages:
        return NormalizedDocument(outline=doc.outline)

    # Pre-clean pages
    cleaned_page_texts = [
        _clean_whitespace_and_hyphenation(_clean_unicode_and_controls(page.text))
        for page in doc.pages
    ]

    # De-duplicate headers/footers for multi-page documents
    if len(doc.pages) >= 3 and any(p.page is not None for p in doc.pages):
        cleaned_page_texts = _deduplicate_headers_footers(cleaned_page_texts)

    segments: list[NormalizedSegment] = []
    full_text_parts: list[str] = []
    current_offset = 0

    for idx, page in enumerate(doc.pages):
        page_text = cleaned_page_texts[idx]
        if not page_text:
            continue

        # Check if there is already text before this segment
        if full_text_parts:
            # We will join with "\n\n"
            current_offset += 2

        start_offset = current_offset
        end_offset = start_offset + len(page_text)
        current_offset = end_offset

        segments.append(
            NormalizedSegment(
                text=page_text,
                page=page.page,
                heading=page.heading,
                char_start=start_offset,
                char_end=end_offset,
            )
        )
        full_text_parts.append(page_text)

    assembled_full_text = "\n\n".join(full_text_parts)

    return NormalizedDocument(
        segments=segments,
        full_text=assembled_full_text,
        outline=doc.outline,
    )

