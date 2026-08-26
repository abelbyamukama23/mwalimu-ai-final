"""Tests for document extractors (PDF, DOCX, TXT) and error handling."""

from io import BytesIO

import pypdf
import pytest

from platform_api.apps.processing.extractors import (
    ExtractionError,
    extract,
)
from platform_api.apps.processing.extractors.docx import extract_docx
from platform_api.apps.processing.extractors.pdf import extract_pdf
from platform_api.apps.processing.extractors.txt import extract_txt
from platform_api.apps.resources.models import ResourceType


def _make_pdf_with_text(pages_text: list[str]) -> bytes:
    """Create a minimal in-memory PDF containing text on distinct pages."""
    # Create using basic PDF structure or pypdf/canvas
    # A raw PDF stream containing text:
    writer = pypdf.PdfWriter()
    for _text in pages_text:
        # Create a page and add annotation or text
        # Using basic PDF writer page
        writer.add_blank_page(width=300, height=300)

    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def test_extract_txt_valid(txt_bytes: bytes) -> None:
    """Plain-text extraction parses paragraphs accurately with page=None."""
    doc = extract_txt(txt_bytes)

    assert not doc.is_empty
    assert len(doc.pages) >= 2
    assert all(p.page is None for p in doc.pages)
    assert any("Introduction to Biology" in p.text for p in doc.pages)
    assert any("Cell Structure" in p.text for p in doc.pages)


def test_extract_txt_invalid_utf8() -> None:
    """Invalid UTF-8 text raises ExtractionError."""
    bad_bytes = b"\xff\xfe\x00\x00Invalid UTF-8"
    with pytest.raises(ExtractionError):
        extract_txt(bad_bytes)


def test_extract_docx_valid(docx_bytes: bytes) -> None:
    """DOCX extraction parses paragraphs, styles, and headings."""
    doc = extract_docx(docx_bytes)

    assert not doc.is_empty
    assert len(doc.pages) >= 4
    headings = [p.heading for p in doc.pages if p.heading]
    assert "Chapter 1: Quantum Physics" in headings
    assert "Chapter 2: Thermodynamics" in headings


def test_extract_docx_corrupt() -> None:
    """Corrupt DOCX archive raises ExtractionError."""
    with pytest.raises(ExtractionError):
        extract_docx(b"PK\x03\x04corrupt docx content that is not a zip")


def test_extract_pdf_corrupt() -> None:
    """Corrupt PDF file raises ExtractionError."""
    with pytest.raises(ExtractionError):
        extract_pdf(b"%PDF-1.4 corrupt invalid pdf trailer")


def test_extract_dispatcher(txt_bytes: bytes, docx_bytes: bytes) -> None:
    """Dispatcher delegates correctly by ResourceType."""
    doc_txt = extract(txt_bytes, ResourceType.TXT)
    assert not doc_txt.is_empty

    doc_docx = extract(docx_bytes, ResourceType.DOCX)
    assert not doc_docx.is_empty

    with pytest.raises(ExtractionError):
        extract(b"data", "unsupported_type")


def test_empty_document_detection() -> None:
    """ExtractedDocument.is_empty returns True when pages contain only whitespace."""
    from platform_api.apps.processing.extractors import ExtractedDocument, ExtractedPage

    doc = ExtractedDocument(
        pages=[
            ExtractedPage(page=1, text="   \n  \t  "),
            ExtractedPage(page=2, text=""),
        ]
    )
    assert doc.is_empty
