"""Deterministic back-of-book subject index detector and entry parser."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

from .extractors import ExtractedPage, OutlineNode


@dataclass(frozen=True)
class ParsedIndexEntry:
    """A parsed subject index entry mapping a term to physical document page numbers."""

    term: str
    normalized_term: str
    subterm: str | None
    raw_page_references: str
    target_physical_pages: list[int] = field(default_factory=list)


def normalize_index_term(term: str) -> str:
    """Deterministically normalize an index term for case/punctuation-insensitive lookup.

    Rules:
    - Unicode NFC normalization
    - Case folding (lower)
    - Collapse multiple spaces/tabs
    - Strip leading/trailing punctuation and dot leaders
    - Retain internal alphanumeric keywords and spaces
    """
    if not term:
        return ""
    # Unicode normalize
    t = unicodedata.normalize("NFC", term)
    # Remove control characters
    t = "".join(
        c
        for c in t
        if c in ("\n", "\t", " ") or not unicodedata.category(c).startswith("C")
    )
    # Strip dot leaders and trailing commas/colons
    t = re.sub(r"[.\s…]+$", "", t)
    t = re.sub(r"^[.\s…]+", "", t)
    # Lowercase
    t = t.lower().strip()
    # Normalize internal hyphens and underscores to spaces for consistent matching
    t = re.sub(r"[-_]+", " ", t)
    # Collapse multiple whitespace
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def parse_page_references_to_labels(raw_ref: str) -> list[str]:
    """Parse raw page reference string into ordered printed page labels.

    Preserves Roman numerals (e.g. 'iv'), alphanumeric labels ('A-1'),
    and expands numeric ranges ('42–45' -> ['42', '43', '44', '45']).
    """
    if not raw_ref:
        return []

    cleaned = re.sub(r"^[.\s…]+", "", raw_ref.strip())
    cleaned = re.sub(r"[.\s…]+$", "", cleaned)

    labels: list[str] = []
    parts = re.split(r"[,;]+", cleaned)

    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Check for numeric range: start - end or start – end (en-dash, em-dash, hyphen)
        range_match = re.match(r"^(\d{1,5})\s*[-–—]\s*(\d{1,5})$", part)
        if range_match:
            try:
                start_p = int(range_match.group(1))
                end_p = int(range_match.group(2))
                if 0 < start_p <= end_p and (end_p - start_p) <= 200:
                    for p in range(start_p, end_p + 1):
                        labels.append(str(p))
                elif 0 < start_p:
                    labels.append(str(start_p))
            except ValueError:
                pass
            continue

        # Check for single label: integer, Roman numeral, or alphanumeric (e.g. "6", "iv", "A-1")
        item_match = re.match(r"^([a-zA-Z0-9\-_]+)$", part)
        if item_match:
            labels.append(item_match.group(1))

    return labels


def resolve_page_labels_to_physical(
    labels: Sequence[str],
    page_map: dict[str, int] | None = None,
) -> list[int]:
    """Resolve printed page labels to 1-based physical page numbers.

    Rules:
    - If page_map is provided: look up normalized label in map.
      If a label is not found in page_map, do NOT fabricate a physical page.
    - If page_map is None: fallback to parsing integer directly if numeric.
    """
    if not labels:
        return []

    resolved: set[int] = set()
    for lbl in labels:
        norm = lbl.strip().lower()
        if page_map is not None:
            if norm in page_map:
                resolved.add(page_map[norm])
        else:
            if norm.isdigit():
                val = int(norm)
                if val > 0:
                    resolved.add(val)

    return sorted(resolved)


def parse_page_references(
    raw_ref: str,
    page_map: dict[str, int] | None = None,
) -> list[int]:
    """Parse comma-separated and hyphen/en-dash ranged page strings into integer physical pages.

    Examples:
        "6, 27, 103" -> [6, 27, 103]
        "42–45" -> [42, 43, 44, 45]
        "5, 7-9, 12" -> [5, 7, 8, 9, 12]
        "..... 45, 47" -> [45, 47]
    """
    labels = parse_page_references_to_labels(raw_ref)
    return resolve_page_labels_to_physical(labels, page_map=page_map)


def _is_non_index_heading(title: str) -> bool:
    """Identify headings that must NEVER be classified as a subject index."""
    t = title.strip().lower()
    return bool(
        re.search(
            r"\b(?:bibliography|references|works cited|glossary|table of contents|contents|appendix)\b",
            t,
        )
    )


def _is_index_heading(title: str) -> bool:
    """Identify headings that explicitly declare a subject or general index."""
    t = title.strip().lower()
    if _is_non_index_heading(t):
        return False
    return bool(
        re.match(
            r"^(?:subject\s+index|general\s+index|topic\s+index|alphabetical\s+index|index\s+of\s+subjects|index\s+of\s+terms|index)$",
            t,
        )
    )


def detect_index_pages(
    pages: Sequence[ExtractedPage],
    outline: Sequence[OutlineNode] | None = None,
) -> list[ExtractedPage]:
    """Identify pages containing the back-of-book subject index from extraction."""
    if not pages:
        return []

    # Priority 1: Check outline nodes for explicit index headings
    if outline:
        for node in outline:
            if _is_index_heading(node.title):
                p_start = node.page_start
                p_end = node.page_end or p_start
                if p_start is not None:
                    matched = [
                        p
                        for p in pages
                        if p.page is not None
                        and p.page >= p_start
                        and (p_end is None or p.page <= p_end)
                    ]
                    if matched:
                        return matched

    # Priority 2: Inspect page content (preferring rear pages)
    index_pages: list[ExtractedPage] = []
    in_index_region = False

    for page in pages:
        lines = [line.strip() for line in page.text.split("\n") if line.strip()]
        if not lines:
            continue

        first_few_lines = " ".join(lines[:3]).lower()

        # Check if page starts an index section
        if any(_is_index_heading(line.lower()) for line in lines[:2]) or (
            "index" in first_few_lines and not _is_non_index_heading(first_few_lines)
        ):
            in_index_region = True

        # Check if a non-index section starts (e.g. Bibliography or new document)
        if in_index_region and any(
            _is_non_index_heading(line.lower()) for line in lines[:2]
        ):
            in_index_region = False

        if in_index_region:
            index_pages.append(page)
            continue

        # Heuristic: Check if page has dense pattern of index entries (term ... page_numbers)
        # e.g. at least 4 lines matching "term ... \d+" or "term, \d+"
        entry_pattern_count = 0
        for line in lines:
            if re.search(
                r"^[\w\s\(\)\-–,']{2,40}[.\s…\t,]+(?:\d{1,4}(?:[,\s–-]+\d{1,4})*)\s*$",
                line,
            ):
                entry_pattern_count += 1

        if entry_pattern_count >= 5 and not _is_non_index_heading(first_few_lines):
            index_pages.append(page)

    return index_pages


def parse_index_entries(
    index_pages: Sequence[ExtractedPage],
    page_map: dict[str, int] | None = None,
) -> list[ParsedIndexEntry]:
    """Parse extracted index pages into structured ParsedIndexEntry objects."""
    entries: list[ParsedIndexEntry] = []
    current_parent_term: str | None = None

    # Line pattern: term [dot-leaders / commas / tabs / spaces] [page numbers]
    # e.g. "activation energy ........ 6, 27, 103" or "activation energy, 6, 27, 103"
    entry_re = re.compile(
        r"^(?P<indent>\s*)(?P<term>[\w\s\(\)\-–'/]+?)[.\s…\t,]+(?P<pages>\d{1,5}(?:[,\s–\-\d]+)*)\s*$"
    )

    for page in index_pages:
        for raw_line in page.text.split("\n"):
            if not raw_line.strip():
                continue

            # Skip header line like "SUBJECT INDEX" or single-letter alphabet dividers like "A", "B", "C"
            if _is_index_heading(raw_line.strip()) or re.match(
                r"^[A-Z]$", raw_line.strip()
            ):
                continue

            # Check for parent term without page numbers (e.g. "reaction rates")
            if (
                not raw_line.startswith(" ")
                and not raw_line.startswith("\t")
                and not re.search(r"\d", raw_line)
            ):
                parent_candidate = raw_line.strip()
                if len(parent_candidate) > 1:
                    current_parent_term = parent_candidate
                continue

            m = entry_re.match(raw_line)
            if not m:
                continue

            indent = m.group("indent")
            term_text = m.group("term").strip()
            pages_raw = m.group("pages").strip()

            target_pages = parse_page_references(pages_raw, page_map=page_map)
            if not target_pages:
                continue


            # Determine if this is a subentry or top-level entry
            is_subentry = bool(indent and len(indent) >= 2) or raw_line.startswith(
                "\t"
            )

            if is_subentry and current_parent_term:
                parent = current_parent_term
                sub = term_text
                norm_term = normalize_index_term(f"{parent} {sub}")
                entries.append(
                    ParsedIndexEntry(
                        term=parent,
                        normalized_term=norm_term,
                        subterm=sub,
                        raw_page_references=pages_raw,
                        target_physical_pages=target_pages,
                    )
                )
            else:
                current_parent_term = term_text
                norm_term = normalize_index_term(term_text)
                entries.append(
                    ParsedIndexEntry(
                        term=term_text,
                        normalized_term=norm_term,
                        subterm=None,
                        raw_page_references=pages_raw,
                        target_physical_pages=target_pages,
                    )
                )

    return entries
