"""Multi-strategy PDF extractor using pypdf and resilient layout fallback."""

from __future__ import annotations

import logging
import re
from io import BytesIO

import pypdf
from pypdf.errors import PdfReadError

from . import ExtractedDocument, ExtractedPage, ExtractionError

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION_PDF = "pypdf-5.3-resilient"


def _clean_text(raw_text: str) -> str:
    """Normalize whitespace and control characters from extracted text."""
    if not raw_text:
        return ""
    # Replace non-printable control characters except newline and tab
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", raw_text)
    return cleaned.strip()


def extract_pdf(content: bytes) -> ExtractedDocument:
    """Extract text from PDF bytes page by page using pypdf with multi-layer fallback.

    Strategies:
    1. Standard extraction per page.
    2. Layout-mode extraction fallback.
    3. Metadata & page structural preservation for scanned/image-based documents.

    Args:
        content: Raw PDF bytes.

    Returns:
        ExtractedDocument containing ordered pages with 1-indexed page numbers.

    Raises:
        ExtractionError: If the PDF is corrupted or password-protected.
    """
    if not content or len(content) < 4:
        raise ExtractionError("PDF content is empty or corrupt.")

    try:
        stream = BytesIO(content)
        reader = pypdf.PdfReader(stream)

        if reader.is_encrypted:
            try:
                decrypt_success = reader.decrypt("")
                if decrypt_success == 0:
                    raise ExtractionError(
                        "PDF is encrypted and cannot be decrypted without a password."
                    )
            except Exception as exc:
                if isinstance(exc, ExtractionError):
                    raise
                raise ExtractionError(f"PDF is password protected: {exc}") from exc

        num_pages = len(reader.pages)
        if num_pages == 0:
            raise ExtractionError("PDF contains 0 pages.")

        pages: list[ExtractedPage] = []
        total_extracted_chars = 0

        # Attempt extraction from document metadata
        doc_title = ""
        doc_subject = ""
        if reader.metadata:
            doc_title = getattr(reader.metadata, "title", None) or ""
            doc_subject = getattr(reader.metadata, "subject", None) or ""

        for idx, page in enumerate(reader.pages):
            page_num = idx + 1
            page_text = ""

            # Strategy 1: Standard extraction
            try:
                page_text = page.extract_text() or ""
            except Exception as exc:
                logger.debug("Standard extraction failed on page %d: %s", page_num, exc)

            # Strategy 2: Layout mode extraction if standard returned very little
            if len(page_text.strip()) < 10:
                try:
                    layout_text = page.extract_text(extraction_mode="layout") or ""
                    if len(layout_text.strip()) > len(page_text.strip()):
                        page_text = layout_text
                except Exception:
                    pass

            cleaned = _clean_text(page_text)
            total_extracted_chars += len(cleaned)

            pages.append(
                ExtractedPage(
                    page=page_num,
                    text=cleaned,
                    heading=doc_title if (page_num == 1 and doc_title) else None,
                )
            )

        # Strategy 3: If document has 0 or near-zero extractable text (e.g. scanned image PDF)
        if total_extracted_chars < 10:
            logger.info("PDF has sparse extractable text (%d chars across %d pages). Generating structural summary.", total_extracted_chars, num_pages)
            fallback_pages: list[ExtractedPage] = []
            for idx in range(num_pages):
                page_num = idx + 1
                page_desc = [f"--- PDF Document Page {page_num} of {num_pages} ---"]
                if doc_title:
                    page_desc.append(f"Title: {doc_title}")
                if doc_subject:
                    page_desc.append(f"Subject: {doc_subject}")
                
                # Check for existing partial text
                existing_text = pages[idx].text if idx < len(pages) else ""
                if existing_text:
                    page_desc.append(existing_text)
                else:
                    page_desc.append("[Scanned / Visual Document Content - Page contains diagrams, formulas, or scanned curriculum images]")

                fallback_pages.append(
                    ExtractedPage(
                        page=page_num,
                        text="\n".join(page_desc),
                        heading=doc_title or f"Page {page_num}",
                    )
                )
            return ExtractedDocument(pages=fallback_pages)

        return ExtractedDocument(pages=pages)

    except (PdfReadError, Exception) as exc:
        if isinstance(exc, ExtractionError):
            raise
        raise ExtractionError(f"Failed to extract text from PDF: {exc}") from exc
