# Citation Precision & Synthesized Evidence Assembly

This document describes the engineering architecture, domain models, and guarantees of Stage 10 in Mwalimu's Hierarchical Book-Reading and Knowledge Retrieval Engine.

---

## 1. Motivation: From Chunk Retrieval to Grounded Quotation

Prior to Stage 10, the Knowledge Gateway retrieved answer-ready chunks and clusters (Stages 1–9). However, downstream LLM reasoning in the Agent Service faced two primary operational hurdles:
1. **Paragraph-Level Ambiguity**: Chunks are typically 200–300 tokens long. Asking an LLM to quote from a paragraph without sentence-level grounding increases the risk of imprecise quotes or accidental hallucination.
2. **Physical Page Disconnect**: Provenance reports `page_start` and `page_end` as physical document indices (e.g. physical page 48). Textbooks, however, contain unnumbered front matter, preface pages, and appendices, meaning the physical index diverged from the printed page number (e.g. Page 36) in the student's hands.

Stage 10 solves both issues deterministically:
- **Pinpoints the exact answer sentence(s)** within each chunk with character offsets and role classifications.
- **Resolves physical pages to printed page labels** using `DocumentPageMap`.
- **Synthesizes multi-chunk derivations** into cohesive, ordered calculation units.

---

## 2. Extractive Span Pinpointing (`extract_answer_spans`)

Span pinpointing breaks each chunk into sentences using a Unicode-safe tokenizer that protects:
- Common academic abbreviations (`e.g.`, `i.e.`, `Fig.`, `et al.`, `Dr.`, `vs.`, `pp.`).
- Decimal numbers (`3.14`).

Each sentence is evaluated in-memory against the query's normalized concepts and detected intent:

| Query Intent | Extracted Span Roles | Confidence |
|---|---|---|
| **DEFINITIONAL** | `primary_definition` (*"is defined as..."*, *"refers to..."*), `symbol_specification` (*"designated by the symbol..."*) | $0.92 - 0.96$ |
| **QUANTITATIVE** | `formula_definition` ($k = A e^{-E_a/RT}$), `numerical_values` (*"Given: T = 300 K..."*), `calculation_solution` (*"Solution: k = 2.4e-3..."*) | $0.89 - 0.95$ |
| **PROCEDURAL** | `procedural_step` (*"Step 1"*, *"Step 2"*), `procedural_outcome` | $0.90 - 0.95$ |
| **COMPARATIVE** | `contrastive_statement` (*"whereas"*, *"in contrast"*, *"difference between"*) | $0.95$ |
| **CAUSAL** | `causal_mechanism` (*"because ... which causes ..."*), `causal_link` | $0.88 - 0.95$ |
| **OVERVIEW** | `overview_intro` (*"in this chapter"*, *"overview of"*) | $0.92$ |

### Data Model
```python
@dataclass(frozen=True)
class EvidenceAnswerSpan:
    text: str
    char_start: int
    char_end: int
    role: str
    confidence: float
```

---

## 3. Printed Page Citation Resolution (`resolve_chunk_citations`)

Using the `DocumentPageMap` model from Stage 6, Stage 10 batch-resolves physical document page numbers into printed textbook citations in a **single database query**:

```python
qs = DocumentPageMap.objects.filter(
    resource__library_id__in=scope.authorized_library_ids,
    resource_id__in=resource_ids,
    physical_page__in=physical_pages,
    processing_run__is_active=True,
    processing_run__status="ready",
)
```

### Citation Formatting Rules
- **Single Page Match**: If physical 48 maps to printed `"36"`, emits:
  `"{Resource.name}, {section}, p. 36"`
- **Multi-Page Range**: If physical 50–51 map to printed `"38"` and `"39"`, emits:
  `"{Resource.name}, {section}, pp. 38–39"`
- **Graceful Fallback**: If no mapping exists (or unmapped document), falls back safely to physical page numbers:
  `"{Resource.name}, {section}, p. 15"`

---

## 4. Multi-Chunk Derivation Synthesis

For complex multi-chunk quantitative derivations and worked examples (spanning adaptive context expansion $\pm 2$), `synthesize_derivation_cluster` aggregates the contiguous sequence into a unified object:

```json
{
  "core_chunk_id": "...",
  "is_complete_derivation": true,
  "formatted_citation": "General Chemistry, Chapter 14: Kinetics, pp. 38–39",
  "derivation_steps": [
    { "step": 1, "role": "formula_definition", "text": "k = A * exp(-Ea/RT)", "sequence": 1 },
    { "step": 2, "role": "numerical_values", "text": "Substitute values: T1 = 300 K, T2 = 350 K...", "sequence": 2 },
    { "step": 3, "role": "calculation_solution", "text": "Solution: Ea = 52.3 kJ/mol.", "sequence": 3 }
  ]
}
```

---

## 5. Architectural & Performance Guarantees

1. **Zero Breaking Changes to Provenance**: The 14-field `ProvenanceDTO` contract is preserved verbatim. New fields (`citation` and `answer_spans`) are purely additive on `SearchResultItemDTO`.
2. **Zero N+1 Queries**: All printed page labels for the top-$k$ results are fetched in a single batch `IN (...)` query.
3. **Zero LLMs**: Span extraction, sentence tokenization, and citation resolution run 100% deterministically in Python ($< 0.1\text{ ms}$ overhead).
4. **Server-Authoritative Scope**: Page maps and citations are scoped by `authorized_library_ids` and `authorized_resource_ids`, preventing cross-library leakage.
