# Evidence Quality & Answer-Ready Retrieval

This document describes the engineering design, evidence-scoring model, and architectural guarantees of Stage 9 in Mwalimu's Knowledge Retrieval Engine.

---

## 1. Objective: "Relevant" vs "Answer-Ready"

Traditional search and retrieval pipelines evaluate passages primarily for semantic similarity (vector distance) and keyword presence (lexical BM25 / tsvector). However, a passage can be highly relevant while still offering poor evidence for answering a learner's question.

### Concrete Example
**Learner Query**: *"What is activation energy?"*

| Candidate Passage | Evidence Role | Retrieval Action |
|---|---|---|
| **A**: *"Activation energy is the minimum energy required for reactant molecules to undergo a successful collision."* | Direct definition | **Rank #1 (Answer-Ready)** |
| **B**: *"Because the activation energy is high, the reaction occurs slowly at room temperature."* | Explanatory consequence | Demoted relative to A |
| **C**: *"The activation energy can be represented by Ea in the Arrhenius equation."* | Supporting detail | Demoted relative to A |
| **D**: *"Temperature affects the rate constant according to the Arrhenius equation."* | Related context | Demoted relative to A |

Stage 9 introduces an in-memory, deterministic **Evidence Quality Layer** that differentiates between mere topical overlap and direct, answer-ready evidence.

---

## 2. Evidence Quality Model (`EvidenceQuality`)

Evidence quality is captured in an immutable domain object:

```python
@dataclass(frozen=True)
class EvidenceQuality:
    directness: float           # 0.0 to 1.0 (addresses query concept directly)
    completeness: float         # 0.0 to 1.0 (sufficiency of evidence)
    intent_alignment: float     # 0.0 to 1.0 (satisfies intent requirements)
    concept_coverage: float     # 0.0 to 1.0 (fraction of query concepts present)
    answer_marker_score: float  # 0.0 to 1.0 (answer cues present)
    structural_authority: float # 0.0 to 1.0 (heading / level / position authority)
    quality_score: float        # Composite quality in [0.0, 1.0]
    evidence_bonus: float       # Bounded bonus in [0.0, 0.08]
    reasons: tuple[str, ...]    # Explainable signals found
```

---

## 3. Evidence Signals & Intent-Specific Behavior

Evidence evaluation is tailored to the detected `QueryIntent`:

### A. DEFINITIONAL
- **Prioritizes**: Explicit definition sentences (`"is defined as"`, `"refers to"`, `"is the minimum/amount/rate"`, proximate concept definition verbs).
- **Penalizes**: Passages merely describing consequences (`"because Ea is high..."`), examples (`"for example..."`), or applications.

### B. QUANTITATIVE
- **Prioritizes**: Complete calculations (`equation + numerical values + units + solution`), explicit step markers (`"Given:"`, `"Using:"`, `"Therefore"`).
- **Penalizes**: Descriptive prose without quantitative equations or solutions.

### C. PROCEDURAL
- **Prioritizes**: Ordered instruction steps (`"Step 1"`, `"first"`, `"then"`, `"next"`), worked example markers (`"worked example"`, `"solution:"`), and explicit action verbs (`"calculate"`, `"substitute"`).
- **Penalizes**: High-level theoretical discussions lacking procedural steps.

### D. COMPARATIVE
- **Prioritizes**: Passages addressing *both* compared entities alongside contrast markers (`"whereas"`, `"while"`, `"in contrast"`, `"difference between"`).
- **Penalizes**: Passages discussing only one side of the comparison.

### E. CAUSAL
- **Prioritizes**: Full mechanistic chains linking cause to outcome (`"because reactant molecules gain kinetic energy, leading to a greater collision frequency..."`).
- **Penalizes**: Factual statements lacking mechanistic depth (`"Reaction rates increase with temperature."`).

### F. OVERVIEW
- **Prioritizes**: Chapter introductions, summaries, and foundational sections (`"In this chapter"`, `"Overview of..."`, `"Introduction"`).
- **Penalizes**: Deep leaf subsections that repeat keywords without broad context.

### G. Concept Coverage
Leverages Stage 8's normalized concepts. Chunks containing multiple key concepts (e.g. *temperature* + *rate constant* + *Arrhenius equation*) receive higher coverage scores than chunks containing only one.

---

## 4. Ranking Formula

The ranking pipeline integrates semantic relevance, lexical match, intent alignment, and evidence quality:

$$\text{base\_score} = 0.65 \cdot \text{vector\_similarity} + 0.35 \cdot \text{norm\_lexical}$$

$$\text{final\_score} = \min(1.0, \text{base\_score} + \text{intent\_bonus} + \text{evidence\_bonus})$$

### Bounding Guarantees
- $\text{intent\_bonus} \le +0.05$
- $\text{evidence\_bonus} \le +0.08$
- $\text{final\_score} \in [0.0, 1.0]$
- **Authoritative Semantic Relevance**: The base hybrid score remains authoritative; evidence quality acts as a decisive reranking prior between candidate matches without overwhelming semantic relevance.
- **Recall Preservation**: Chunks with lower evidence quality receive zero bonus, but are never hard-filtered or removed.

---

## 5. Multi-Chunk Answer-Ready Clusters

When evidence is distributed across sequential chunks (e.g. in multi-step derivations: Step 1 $\rightarrow$ Step 2 $\rightarrow$ Calculation $\rightarrow$ Solution), `evaluate_cluster_evidence` analyzes the expanded sequence window:
- Evaluates whether the contiguous cluster forms a complete, answer-ready unit.
- Reports `answer_ready_cluster: true` in response metadata.
- Core chunk remains the primary anchor with rank #1 in provenance.

---

## 6. Performance & Architectural Guarantees

1. **Zero Database Round Trips**: Operates purely in-memory on retrieved candidate DTOs ($< 0.1\text{ ms}$ CPU overhead).
2. **Strict Boundary & Tenant Isolation**: Only already-authorized chunks within `EffectiveRetrievalScope` are evaluated.
3. **14-Field Provenance Intact**: No changes to the provenance contract.
4. **Agent Service Boundary**: Evidence evaluation is performed in the Platform API; Agent Service continues receiving the standard retrieval response without modification.
