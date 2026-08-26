"""DOCX extractor using python-docx."""

from __future__ import annotations

from io import BytesIO

import docx

from . import ExtractedDocument, ExtractedPage, ExtractionError

EXTRACTOR_VERSION_DOCX = "docx-1"


def extract_docx(content: bytes) -> ExtractedDocument:
    """Extract paragraphs and structural headings from DOCX bytes.

    Args:
        content: Raw DOCX bytes.

    Returns:
        ExtractedDocument containing paragraphs with heading associations.

    Raises:
        ExtractionError: If the DOCX archive is invalid or unreadable.
    """
    try:
        stream = BytesIO(content)
        doc = docx.Document(stream)

        pages: list[ExtractedPage] = []
        current_heading: str | None = None

        for paragraph in doc.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue

            style_name = getattr(paragraph.style, "name", "") or ""
            is_heading = style_name.startswith("Heading") or style_name.lower() in (
                "title",
                "subtitle",
            )

            if is_heading:
                current_heading = text
                pages.append(
                    ExtractedPage(
                        page=None,
                        text=text,
                        heading=current_heading,
                    )
                )
            else:
                pages.append(
                    ExtractedPage(
                        page=None,
                        text=text,
                        heading=current_heading,
                    )
                )

        # Also extract table text if present
        for table in doc.tables:
            for row in table.rows:
                row_texts = [
                    cell.text.strip() for cell in row.cells if cell.text.strip()
                ]
                if row_texts:
                    pages.append(
                        ExtractedPage(
                            page=None,
                            text=" | ".join(row_texts),
                            heading=current_heading,
                        )
                    )

        return ExtractedDocument(pages=pages)
    except Exception as exc:
        raise ExtractionError(f"Failed to extract text from DOCX: {exc}") from exc
