# ADR-005: Chunking Strategy and Provenance Fields

## Status

Accepted

## Context

Document content must be segmented into coherent chunks suitable for vector embedding and context retrieval. Agent workflows require exact, verifiable provenance (page numbers, section headings, character offsets) to cite grounded evidence.

## Decision

We implement a deterministic, internal pure-Python chunker without external framework dependencies.

### Target Parameters and Strategy

- **Target Size**: ~2000 characters (~500 tokens estimated as `ceil(len(text)/4)`).
- **Target Overlap**: ~300 characters (~15%).
- **Boundary Hierarchy**: Paragraph breaks (`\n\n`) → sentence boundaries (`. `, `? `, `! `) → hard character cuts.
- **Page Isolation**: Chunks must not cross page boundaries silently; each chunk records `page_start` and `page_end`.
- **Section Association**: The nearest preceding section heading is associated with the chunk in `section` metadata without prepending text into the chunk content.
- **Provenance Attributes**: Every `DocumentChunk` persists:
  - `sequence` (ordered 0-indexed position within run)
  - `char_start` and `char_end` (relative to the full normalized text)
  - `page_start` and `page_end` (nullable for non-paginated formats)
  - `section` (heading title or hierarchy)
  - `token_count` (estimated character-ratio metric)
  - `content_sha256` (SHA-256 digest of chunk text for integrity)

### Determinism Invariant

Identical `(source_checksum, pipeline_version, chunker_version)` always produces byte-identical chunks with identical sequences, offsets, and checksums.

## Consequences

### Positive

- Complete auditability and citations for future agent answer synthesis.
- Predictable, deterministic chunk boundaries across worker restarts.
- High performance without tokenization library bottlenecks or network calls.

### Negative

- Character-count approximations (~4 chars/token) may slightly vary in token count across different language scripts.

## Alternatives Considered

- **LangChain RecursiveCharacterTextSplitter**: Rejected per ADR-002; bespoke chunker provides exact character and page offset tracking without third-party frameworks.
- **Semantic / LLM-based chunking**: Rejected due to high latency, cost, and non-deterministic behavior.

## Related Decisions

- ADR-003: Extraction Library Selection.
- ADR-007: Processing Identity, Idempotency, and Versioned Embeddings.
