"""PDF extractor using pypdf."""

from __future__ import annotations

from io import BytesIO

import pypdf
from pypdf.errors import PdfReadError

from . import ExtractedDocument, ExtractedPage, ExtractionError

EXTRACTOR_VERSION_PDF = "pypdf-5"


def extract_pdf(content: bytes) -> ExtractedDocument:
    """Extract text from PDF bytes page by page using pypdf.

    Args:
        content: Raw PDF bytes.

    Returns:
        ExtractedDocument containing ordered pages with 1-indexed page numbers.

    Raises:
        ExtractionError: If the PDF is corrupted, encrypted, or cannot be read.
    """
    try:
        stream = BytesIO(content)
        reader = pypdf.PdfReader(stream)

        if reader.is_encrypted:
            try:
                # Try decrypting with empty password if permitted
                decrypt_success = reader.decrypt("")
                if decrypt_success == 0:
                    raise ExtractionError(
                        "PDF is encrypted and cannot be decrypted without a password."
                    )
            except Exception as exc:
                raise ExtractionError(f"PDF is password protected: {exc}") from exc

        pages: list[ExtractedPage] = []
        for idx, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            pages.append(
                ExtractedPage(
                    page=idx + 1,
                    text=page_text,
                    heading=None,
                )
            )

        return ExtractedDocument(pages=pages)
    except (PdfReadError, Exception) as exc:
        if isinstance(exc, ExtractionError):
            raise
        raise ExtractionError(f"Failed to extract text from PDF: {exc}") from exc
