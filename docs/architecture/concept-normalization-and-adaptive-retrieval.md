# Concept Normalization & Adaptive Retrieval Hardening

This document describes the engineering design and operational principles of Stage 8 in Mwalimu's Hierarchical Book-Reading and Knowledge Retrieval Engine.

---

## 1. Why Generic Stemming Was Deliberately Avoided

Traditional aggressive algorithmic stemmers (such as the Porter or Snowball stemmers) apply heuristic suffix stripping designed for general web search or sentiment analysis. In technical and scientific textbook retrieval, aggressive stemming causes catastrophic semantic collapse:
- Stripping `-ic` turns **organic** into **organ**.
- Stripping `-al` turns **general** into **generic**.
- Stripping `-ity` turns **relativity** into **relative**.
- Truncating terms collapses distinct chemical equilibrium constants (**Ka**, **Ksp**, **Kw**, **Kp**) into ambiguous characters.

Mwalimu deliberately avoids algorithmic stemming in favor of a **controlled, conservative morphological normalization layer**:
1. Regular plural-to-singular transformations are only applied to verified English suffixes (`-ies` $\rightarrow$ `-y`, `-es` after sibilants, `-s` for words with length $\ge 4$).
2. Specific academic term pairings are explicitly defined as bidirectional semantic-morphological equivalents (e.g., `catalyst` $\leftrightarrow$ `catalysis`, `reaction` $\leftrightarrow$ `reactions`, `ferment` $\leftrightarrow$ `fermentation`).
3. A protected set of sensitive technical symbols and short words (e.g. `Ka`, `Ksp`, `pH`, `mass`, `gas`) is guaranteed to remain untouched.

---

## 2. How Canonical Concepts Work

Learners frequently ask questions using shorthand notations, symbols, or colloquial variants (e.g. *"What is Ea?"*, *"Explain Kc"*). Textbooks, however, formally organize these topics under canonical academic names (e.g. *"Activation Energy"*, *"The Equilibrium Constant"*).

Mwalimu defines canonical concepts through `ConceptNormalizationResult`:
```python
@dataclass(frozen=True)
class ConceptNormalizationResult:
    original_term: str
    normalized_terms: tuple[str, ...]
    canonical_concepts: tuple[str, ...]
    aliases_applied: tuple[tuple[str, str], ...]
```
When a query contains an alias (such as `Ea` or `Eₐ`), the normalization engine resolves it to its canonical concept form (`activation energy`) without fabricating unexpressed concepts.

---

## 3. How Aliases Are Registered

Technical aliases are registered in an in-memory, deterministic, and versionable registry (`TECHNICAL_ALIAS_REGISTRY` in `knowledge/concept_normalization.py`):
```python
TECHNICAL_ALIAS_REGISTRY = {
    "ea": "activation energy",
    "e_a": "activation energy",
    "eₐ": "activation energy",
    "kc": "equilibrium constant",
    "k_c": "equilibrium constant",
    "δh": "enthalpy change",
    "delta h": "enthalpy change",
    "reaction rate": "reaction rate",
    "arrhenius": "arrhenius equation",
}
```
All entries are case-normalized, whitespace-trimmed, and matched against queries as whole word/symbol tokens.

---

## 4. How Normalization Affects TOC & Index Retrieval

Normalization acts as a **bridge between colloquial/symbolic queries and textbook structure**:
1. **Table of Contents (TOC) Search**:
   In `structure_search.py`, `find_candidate_structure_nodes` tests candidate `DocumentStructureNode` titles against both the original query tokens and the extracted canonical concepts. If a learner asks *"What is Ea?"*, the canonical concept `activation energy` awards full phrase-containment points (+5.0) to sections like *"14.4 Activation Energy and Arrhenius Equation"*.
2. **Back-of-Book Subject Index Search**:
   In `index_search.py`, `find_candidate_index_pages` adds canonical concepts and morphological equivalents to the search phrase set. A query for *"catalyst"* matches index entries indexed as `"catalysis"` or `"catalysts"`, resolving the exact physical pages where that concept is discussed.

---

## 5. How Adaptive Context Expansion Works

Textbook explanations vary in size depending on query intent:
- **Definitional, Conceptual, or Overview Queries**: The default bounded context window of **$\text{sequence} \pm 1$** (maximum 3 contiguous chunks) provides optimal focus without diluting evidence.
- **Procedural and Quantitative Queries**: Multi-step calculations, worked examples, and mathematical derivations frequently span 4–5 contiguous chunks (Problem Statement $\rightarrow$ Formula Identification $\rightarrow$ Variable Substitution $\rightarrow$ Arithmetic Calculation $\rightarrow$ Units & Verification).

When a query's intent is classified as `PROCEDURAL` or `QUANTITATIVE` and the retrieved core chunk contains calculation evidence (such as `"worked example"`, `"solution:"`, `"step 1"`, `"formula"`), Mwalimu adaptively expands the context window to **$\text{sequence} \pm 2$** (up to 5 contiguous chunks).

### Boundary Invariants
Adaptive expansion remains strictly bounded:
- It **never** crosses section or structural node boundaries (`neighbor.structure_node_id == core_node_id`).
- It **never** crosses resource or library boundaries.
- It **never** duplicates chunks.
- Neighbor chunks receive decaying scores ($0.95^w$), ensuring that the core retrieval chunk always retains rank #1.

---

## 6. Why Normalization Is a Soft Prior Rather Than a Hard Filter

A core architectural axiom of Mwalimu is that **discovery priors must never destroy recall**:
- Normalization and technical aliases provide additional matching evidence; they **never** exclude documents, chapters, or index entries that fail to match the alias.
- If a query matches neither an alias nor a morphological equivalent, retrieval falls back gracefully to the standard hybrid vector + lexical search across the authorized scope.
- Level 4 global backfill in `PgVectorRetriever` ensures that unexpected phrasing or non-standard documents remain fully retrievable.
