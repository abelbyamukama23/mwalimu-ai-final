"""Multi-strategy PDF extractor using pypdf and resilient layout fallback."""

from __future__ import annotations

import logging
import re
from io import BytesIO
from typing import Any

import pypdf
from pypdf.errors import PdfReadError

from . import (
    ExtractedDocument,
    ExtractedPage,
    ExtractionError,
    OutlineNode,
    StructureNodeType,
)

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION_PDF = "pypdf-5.3-resilient-hbr1"


def _clean_text(raw_text: str) -> str:
    """Normalize whitespace and control characters from extracted text."""
    if not raw_text:
        return ""
    # Replace non-printable control characters except newline and tab
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", raw_text)
    return cleaned.strip()


def _classify_pdf_node_type(title: str, level: int) -> str:
    """Classify structural node type from title patterns and hierarchy depth."""
    t = title.strip().lower()
    if re.match(r"^(?:part\b|volume\b|book\b)", t):
        return StructureNodeType.PART
    if re.match(r"^(?:chapter\b|ch\.\s*\d+)", t):
        return StructureNodeType.CHAPTER
    if re.match(r"^(?:section\b|sec\.\s*\d+)", t):
        return StructureNodeType.SECTION
    if re.match(r"^(?:subsection\b)", t):
        return StructureNodeType.SUBSECTION
    if re.match(r"^(?:appendix\b)", t):
        return StructureNodeType.APPENDIX
    if re.match(
        r"^(?:preface\b|foreword\b|introduction\b|prologue\b|contents\b|table of contents\b|acknowledgements?\b)",
        t,
    ):
        return StructureNodeType.FRONT_MATTER
    if re.match(
        r"^(?:epilogue\b|afterword\b|glossary\b|bibliography\b|references\b|index\b)",
        t,
    ):
        return StructureNodeType.BACK_MATTER
    if level == 1:
        return (
            StructureNodeType.CHAPTER
            if "chapter" in t
            else StructureNodeType.SECTION
        )
    if level == 2:
        return StructureNodeType.SECTION
    if level >= 3:
        return StructureNodeType.SUBSECTION
    return StructureNodeType.OTHER


def _resolve_destination_page(reader: pypdf.PdfReader, dest: Any) -> int | None:
    """Safely resolve a destination or bookmark object to a 1-indexed page number."""
    try:
        page_num = reader.get_destination_page_number(dest)
        if page_num is not None and page_num >= 0:
            return page_num + 1
    except Exception as exc:
        logger.debug("Failed to resolve destination page number: %s", exc)
    return None


def _parse_outline_items(
    reader: pypdf.PdfReader,
    items: list[Any],
    current_level: int = 1,
) -> list[OutlineNode]:
    """Recursively parse pypdf outline items into OutlineNode trees."""
    nodes: list[OutlineNode] = []
    prev_node: OutlineNode | None = None

    for item in items:
        if isinstance(item, list):
            # Nested children of previous bookmark
            if prev_node is not None:
                child_nodes = _parse_outline_items(
                    reader, item, current_level=current_level + 1
                )
                updated_prev = OutlineNode(
                    title=prev_node.title,
                    level=prev_node.level,
                    node_type=prev_node.node_type,
                    page_start=prev_node.page_start,
                    page_end=prev_node.page_end,
                    sequence=prev_node.sequence,
                    source=prev_node.source,
                    confidence=prev_node.confidence,
                    metadata=prev_node.metadata,
                    children=list(child_nodes),
                )
                nodes[-1] = updated_prev
                prev_node = updated_prev
        else:
            raw_title = getattr(item, "title", None) or str(item)
            title = _clean_text(str(raw_title))
            if not title:
                continue

            page_num = _resolve_destination_page(reader, item)
            node_type = _classify_pdf_node_type(title, current_level)

            node = OutlineNode(
                title=title,
                level=current_level,
                node_type=node_type,
                page_start=page_num,
                page_end=None,
                source="native",
                confidence=1.0 if page_num is not None else 0.8,
                metadata={},
                children=[],
            )
            nodes.append(node)
            prev_node = node

    return nodes


def _assign_sequences_and_ranges(
    nodes: list[OutlineNode],
    num_pages: int,
) -> list[OutlineNode]:
    """Assign deterministic sequences and compute page_end across outline nodes."""
    flat: list[OutlineNode] = []

    def _collect(n_list: list[OutlineNode]) -> None:
        for n in n_list:
            flat.append(n)
            if n.children:
                _collect(n.children)

    _collect(nodes)
    if not flat:
        return []

    seq = 0
    seq_map: dict[int, int] = {}
    page_end_map: dict[int, int | None] = {}

    for idx, node in enumerate(flat):
        seq_map[id(node)] = seq
        seq += 1

        next_page: int | None = None
        for next_node in flat[idx + 1 :]:
            if next_node.level <= node.level and next_node.page_start is not None:
                next_page = next_node.page_start
                break

        if node.page_start is not None:
            if next_page is not None and next_page > node.page_start:
                page_end_map[id(node)] = next_page - 1
            else:
                page_end_map[id(node)] = num_pages
        else:
            page_end_map[id(node)] = None

    def _rebuild(n_list: list[OutlineNode]) -> list[OutlineNode]:
        result = []
        for n in n_list:
            new_children = _rebuild(n.children) if n.children else []
            result.append(
                OutlineNode(
                    title=n.title,
                    level=n.level,
                    node_type=n.node_type,
                    page_start=n.page_start,
                    page_end=page_end_map.get(id(n), n.page_end),
                    sequence=seq_map.get(id(n), 0),
                    source=n.source,
                    confidence=n.confidence,
                    metadata=n.metadata,
                    children=new_children,
                )
            )
        return result

    return _rebuild(nodes)



def _detect_page_labels_from_text(
    pages: list[ExtractedPage],
) -> list[tuple[int, str, str]] | None:
    """Detect printed page numbers from headers/footers when native /PageLabels is absent.

    Requires at least 3 consecutive pages with incrementing numeric sequence.
    """
    num_pages = len(pages)
    if num_pages < 3:
        return None

    candidate_numbers: dict[int, int] = {}
    roman_numbers: dict[int, str] = {}

    for p in pages:
        if p.page is None:
            continue
        lines = [line.strip() for line in p.text.split("\n") if line.strip()]
        if not lines:
            continue

        check_lines = lines[-2:] + lines[:2]
        found_num = False
        for line in check_lines:
            m_num = re.match(r"^(?:page\s+|-\s*)?(\d{1,4})(?:\s*-)?$", line, re.IGNORECASE)
            if m_num:
                candidate_numbers[p.page] = int(m_num.group(1))
                found_num = True
                break
            m_rom = re.match(r"^([ivxlcdm]+)$", line, re.IGNORECASE)
            if m_rom and not found_num:
                roman_numbers[p.page] = m_rom.group(1).lower()

    best_offset: int | None = None
    for phys in sorted(candidate_numbers.keys()):
        val = candidate_numbers[phys]
        off = phys - val
        if (
            phys + 1 in candidate_numbers
            and candidate_numbers[phys + 1] == val + 1
            and phys + 2 in candidate_numbers
            and candidate_numbers[phys + 2] == val + 2
        ):
            best_offset = off
            break

    if best_offset is None or best_offset <= 0:
        return None

    result: list[tuple[int, str, str]] = []
    for p in pages:
        phys = p.page
        if phys is None:
            continue
        if phys <= best_offset:
            lbl = roman_numbers.get(phys, f"front-{phys}")
            result.append((phys, lbl, "detected"))
        else:
            printed_num = phys - best_offset
            result.append((phys, str(printed_num), "detected"))

    return result


def _extract_page_labels(
    reader: pypdf.PdfReader,
    pages: list[ExtractedPage],
) -> list[tuple[int, str, str]]:
    """Extract physical-to-printed page labels using native /PageLabels, headers/footers, or default."""
    num_pages = len(pages)
    if num_pages == 0:
        return []

    # Strategy 1: Native PDF /PageLabels
    try:
        has_native = False
        if hasattr(reader, "trailer") and reader.trailer:
            root = reader.trailer.get("/Root")
            if root is not None:
                root_dict = root.get_object() if hasattr(root, "get_object") else root
                if hasattr(root_dict, "__contains__") and "/PageLabels" in root_dict:
                    has_native = True

        labels = getattr(reader, "page_labels", None)
        if has_native and labels and len(labels) == num_pages:
            return [(i + 1, str(labels[i]), "native") for i in range(num_pages)]
    except Exception as exc:
        logger.debug("Failed to read native PDF /PageLabels: %s", exc)


    # Strategy 2: Conservative detection from headers/footers
    detected = _detect_page_labels_from_text(pages)
    if detected:
        return detected

    # Strategy 3: Default 1:1 physical mapping
    return [(i + 1, str(i + 1), "default") for i in range(num_pages)]


def extract_pdf(content: bytes) -> ExtractedDocument:
    """Extract text and native outline from PDF bytes using pypdf with fallbacks."""
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

        # Strategy 4: Native outline / bookmark hierarchy extraction
        outline_nodes: list[OutlineNode] = []
        try:
            raw_outline = getattr(reader, "outline", None)
            if raw_outline and isinstance(raw_outline, list):
                parsed_outline = _parse_outline_items(
                    reader, raw_outline, current_level=1
                )
                outline_nodes = _assign_sequences_and_ranges(
                    parsed_outline, num_pages
                )
        except Exception as outline_exc:
            logger.warning(
                "Failed to parse PDF outline/bookmarks (continuing without outline): %s",
                outline_exc,
            )
            outline_nodes = []

        # Extract page labels (native / detected / default)
        page_labels = _extract_page_labels(reader, pages)
        lbl_by_phys = {p: l for p, l, _ in page_labels}

        # Strategy 3: If document has 0 or near-zero extractable text (e.g. scanned image PDF)
        if total_extracted_chars < 10:
            logger.info(
                "PDF has sparse extractable text (%d chars across %d pages). "
                "Generating structural summary.",
                total_extracted_chars,
                num_pages,
            )
            fallback_pages: list[ExtractedPage] = []
            for idx in range(num_pages):
                page_num = idx + 1
                page_desc = [f"--- PDF Document Page {page_num} of {num_pages} ---"]
                if doc_title:
                    page_desc.append(f"Title: {doc_title}")
                if doc_subject:
                    page_desc.append(f"Subject: {doc_subject}")

                existing_text = pages[idx].text if idx < len(pages) else ""
                if existing_text:
                    page_desc.append(existing_text)
                else:
                    page_desc.append(
                        "[Scanned / Visual Document Content - Page contains "
                        "diagrams, formulas, or scanned curriculum images]"
                    )

                fallback_pages.append(
                    ExtractedPage(
                        page=page_num,
                        text="\n".join(page_desc),
                        heading=doc_title or f"Page {page_num}",
                        printed_label=lbl_by_phys.get(page_num),
                    )
                )
            return ExtractedDocument(
                pages=fallback_pages,
                outline=outline_nodes,
                page_labels=page_labels,
            )

        updated_pages = [
            ExtractedPage(
                page=p.page,
                text=p.text,
                heading=p.heading,
                printed_label=lbl_by_phys.get(p.page),
            )
            for p in pages
        ]

        return ExtractedDocument(
            pages=updated_pages,
            outline=outline_nodes,
            page_labels=page_labels,
        )

    except (PdfReadError, Exception) as exc:
        if isinstance(exc, ExtractionError):
            raise
        raise ExtractionError(f"Failed to extract text from PDF: {exc}") from exc


