"""Deterministic document chunking engine.

Segments normalized text into chunks (~2000 chars, ~300 overlap)
following the paragraph -> sentence -> hard-cut hierarchy while preserving
provenance (pages, headings, character offsets, SHA-256 digests).
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

from .normalizer import NormalizedDocument

CHUNKER_VERSION_DEFAULT = "1"
DEFAULT_TARGET_SIZE = 2000
DEFAULT_OVERLAP = 300


@dataclass(frozen=True)
class ChunkResult:
    """A deterministic document chunk with complete provenance attributes."""

    sequence: int
    text: str
    token_count: int
    char_start: int
    char_end: int
    page_start: int | None
    page_end: int | None
    section: str | None
    content_sha256: str


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences while preserving trailing punctuation and spaces."""
    # Split on sentence terminals followed by whitespace
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _chunk_text_block(
    text: str,
    base_char_offset: int,
    page: int | None,
    section: str | None,
    target_size: int,
    overlap: int,
) -> list[tuple[str, int, int, int | None, int | None, str | None]]:
    """Chunk a single structural text block (e.g. page or section segment).

    Returns list of tuples:
    (chunk_text, char_start, char_end, page_start, page_end, section)
    """
    if len(text) <= target_size:
        return [
            (text, base_char_offset, base_char_offset + len(text), page, page, section)
        ]

    # Split into paragraphs
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    raw_units: list[str] = []

    for para in paragraphs:
        if len(para) <= target_size:
            raw_units.append(para)
        else:
            # Paragraph is too big, split into sentences
            sentences = _split_into_sentences(para)
            for sentence in sentences:
                if len(sentence) <= target_size:
                    raw_units.append(sentence)
                else:
                    # Sentence is too big, hard slice at boundaries
                    start = 0
                    while start < len(sentence):
                        end = min(start + target_size, len(sentence))
                        if end < len(sentence):
                            # Try to break at a space
                            last_space = sentence.rfind(" ", start, end)
                            if last_space > start + (target_size // 2):
                                end = last_space
                        slice_text = sentence[start:end].strip()
                        if slice_text:
                            raw_units.append(slice_text)
                        start = end

    # Combine units with overlap
    chunks: list[tuple[str, int, int, int | None, int | None, str | None]] = []
    current_unit_idx = 0

    while current_unit_idx < len(raw_units):
        current_chunk_units: list[str] = []
        current_len = 0
        step_idx = current_unit_idx

        while step_idx < len(raw_units):
            unit = raw_units[step_idx]
            projected_len = current_len + (2 if current_chunk_units else 0) + len(unit)

            if projected_len <= target_size or not current_chunk_units:
                current_chunk_units.append(unit)
                current_len = projected_len
                step_idx += 1
            else:
                break

        chunk_content = "\n\n".join(current_chunk_units).strip()

        # Find character offsets in original block
        search_start = 0
        if chunks:
            # We search from somewhere around previous chunk offset
            prev_offset = chunks[-1][1] - base_char_offset
            search_start = max(0, prev_offset)

        found_idx = text.find(chunk_content, search_start)
        if found_idx == -1:
            found_idx = text.find(chunk_content)
        if found_idx == -1:
            found_idx = 0

        chunk_start_abs = base_char_offset + found_idx
        chunk_end_abs = chunk_start_abs + len(chunk_content)

        chunks.append(
            (
                chunk_content,
                chunk_start_abs,
                chunk_end_abs,
                page,
                page,
                section,
            )
        )

        if step_idx >= len(raw_units):
            break

        # Calculate rewind for overlap
        rewind_chars = 0
        next_start_idx = step_idx
        for rewind_idx in range(step_idx - 1, current_unit_idx - 1, -1):
            unit_len = len(raw_units[rewind_idx]) + 2
            if rewind_chars + unit_len <= overlap and rewind_idx < step_idx:
                rewind_chars += unit_len
                next_start_idx = rewind_idx
            else:
                break

        if next_start_idx == current_unit_idx:
            # Ensure progress
            current_unit_idx = step_idx
        else:
            current_unit_idx = next_start_idx

    return chunks


def chunk(
    doc: NormalizedDocument,
    target_size: int = DEFAULT_TARGET_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[ChunkResult]:
    """Chunk a NormalizedDocument into deterministic ChunkResult objects.

    Args:
        doc: Normalized document containing segments and full text.
        target_size: Desired chunk character length (~2000).
        overlap: Desired chunk character overlap (~300).

    Returns:
        Ordered list of ChunkResult instances with sequence starting at 0.
    """
    if not doc.segments or not doc.full_text.strip():
        return []

    raw_chunks: list[tuple[str, int, int, int | None, int | None, str | None]] = []

    # Process segment by segment to preserve page and section boundaries cleanly
    for segment in doc.segments:
        if not segment.text.strip():
            continue

        segment_chunks = _chunk_text_block(
            text=segment.text,
            base_char_offset=segment.char_start,
            page=segment.page,
            section=segment.heading,
            target_size=target_size,
            overlap=overlap,
        )
        raw_chunks.extend(segment_chunks)

    results: list[ChunkResult] = []
    for seq, (text_content, c_start, c_end, p_start, p_end, section_name) in enumerate(
        raw_chunks
    ):
        content_hash = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
        token_estimate = math.ceil(len(text_content) / 4)

        results.append(
            ChunkResult(
                sequence=seq,
                text=text_content,
                token_count=token_estimate,
                char_start=c_start,
                char_end=c_end,
                page_start=p_start,
                page_end=p_end,
                section=section_name,
                content_sha256=content_hash,
            )
        )

    return results
