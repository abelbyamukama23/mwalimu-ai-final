"""Extraction interface and dispatchers for document binaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from platform_api.apps.resources.models import ResourceType

if TYPE_CHECKING:
    pass


class ExtractionError(Exception):
    """Raised when document extraction fails due to corrupt or unreadable files."""


@dataclass(frozen=True)
class ExtractedPage:
    """A single page or structural segment of extracted text."""

    page: int | None
    text: str
    heading: str | None = None


@dataclass(frozen=True)
class ExtractedDocument:
    """Structured representation of extracted document content."""

    pages: list[ExtractedPage] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if no text was extracted across all pages."""
        return not any(page.text.strip() for page in self.pages)


def extract(content: bytes, resource_type: str) -> ExtractedDocument:
    """Extract structured pages and headings from raw document bytes.

    Args:
        content: Raw binary bytes of the document.
        resource_type: Resource type from ResourceType (pdf, docx, txt).

    Returns:
        ExtractedDocument containing ordered pages and structural metadata.

    Raises:
        ExtractionError: When parsing fails due to corruption or format violations.
    """
    if resource_type == ResourceType.PDF:
        from .pdf import extract_pdf

        return extract_pdf(content)
    elif resource_type == ResourceType.DOCX:
        from .docx import extract_docx

        return extract_docx(content)
    elif resource_type == ResourceType.TXT:
        from .txt import extract_txt

        return extract_txt(content)
    else:
        raise ExtractionError(
            f"Unsupported resource type for extraction: {resource_type}"
        )
