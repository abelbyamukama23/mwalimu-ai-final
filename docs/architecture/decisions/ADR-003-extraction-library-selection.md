# ADR-003: Extraction Library Selection

## Status

Accepted

## Context

Mwalimu must extract structured text and provenance from multi-format resource files (PDF, DOCX, TXT) to transform uploaded files into chunks for embedding and vector search. We need parsing libraries that are secure, pure-Python, reliable, maintainable, and preserve structural metadata (pages, headings) without introducing native binary dependencies, subshell executions, or external microservices.

## Decision

We select standard, pure-Python libraries tailored to each supported format:

1. **PDF**: `pypdf` for extracting per-page text (`page.extract_text()`) while tracking 1-indexed page boundaries.
2. **DOCX**: `python-docx` for parsing document paragraphs and extracting structural styles/headings in sequential document order.
3. **TXT**: Python standard library (`str.decode("utf-8")`) for decoding text and splitting paragraphs.

### Failure and Deferred Capabilities

- **Empty Extraction**: If document parsing yields no usable text (such as scanned PDFs without embedded text layers), the processing run is explicitly marked `FAILED` with `error_code=EMPTY_EXTRACTION`. It is never marked `READY` with zero chunks.
- **OCR Deferred**: Optical Character Recognition (e.g. `pytesseract`, `OCRmyPDF`) is deferred to a future milestone.
- **Security Boundary**: Parsing occurs in pure Python. Document content is treated as untrusted data and is never executed, passed to shells, or written to temporary executable locations.

## Consequences

### Positive

- Minimal, lightweight dependency footprint with zero external system binaries required.
- Clear, uniform extraction interface emitting standardized `ExtractedDocument` structures across formats.
- Safe execution isolating untrusted uploaded data.
- Strict error classification preventing ghost/empty resources in the knowledge index.

### Negative

- Scanned PDFs without textual metadata cannot be indexed until OCR capabilities are introduced.
- Complex layout parsing (e.g. multi-column tables, vector graphics) is simplified to sequential text flow.

## Alternatives Considered

- **`pdfplumber` / `PyMuPDF`**: Rejected for initial MVP due to C-extension dependencies and heavier resource overhead.
- **LangChain / LlamaIndex loaders**: Rejected per ADR-002; bespoke pure-Python extractors provide full provenance control without framework bloat.
- **Unstructured / external extraction APIs**: Rejected to avoid external network dependencies and proprietary lock-in.

## Related Decisions

- ADR-002: Dependency and Runtime Architecture.
- ADR-005: Chunking Strategy and Provenance Fields.
