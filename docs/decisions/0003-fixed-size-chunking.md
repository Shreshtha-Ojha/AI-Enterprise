# ADR-0003: Fixed-size chunking with overlap

**Status:** Accepted

## Context

Documents need to be split into smaller pieces before embedding — see
[chunking.md](../learning/chunking.md) for why chunking is necessary at
all. Preprocessing/chunking was a required pipeline stage per the project's
original scope, but *how* to chunk (fixed-size, sentence/paragraph-based,
semantic) was left open — this is a genuine implementation decision, not
one specified in advance.

## Decision

Chunk with a fixed character window (default 500 characters) and a fixed
overlap (default 50 characters) — `ChunkingService` in
`rag/services/chunking.py`.

## Rationale

- **Deterministic and dependency-free.** Given the same input text, the
  same chunks come out every time. No extra model call, no sentence-boundary
  detection, no similarity-threshold tuning.
- **Fast and cheap.** Pure string slicing — the only cost is the embedding
  call that happens afterward regardless of chunking strategy.
- **Predictable chunk size**, which bounds both embedding batch cost and how
  much context gets injected into the LLM prompt per retrieved chunk.
- **"Good enough" to prove a correct end-to-end pipeline first.** The MVP's
  goal was a working ingest → retrieve → generate loop, not chunking
  quality — and chunking is isolated behind a stable contract
  (`ChunkingService.chunk(document_id, filename, text) -> list[Chunk]`), so
  it can be swapped later without touching ingestion, embedding, or storage.

500 characters (~90–120 English words) is small enough to stay topically
coherent, large enough to usually hold a full thought. 50-character overlap
(10%) exists so a sentence that straddles a chunk boundary is still findable
as a coherent unit in at least one chunk — see chunking.md for the full
explanation.

## Consequences / Known limitations

- No semantic awareness — a boundary can fall mid-sentence, mid-table-row,
  or mid-code-block.
- Uniform size regardless of content density.
- Overlapping chunks duplicate content in the index and can cause the same
  passage to surface twice in a single query's results.
- No structural signal (headings, sections) is preserved.

Full limitations and how semantic chunking would replace this are in
[chunking.md](../learning/chunking.md).

## Alternatives considered

**Semantic chunking** (split at sentence/paragraph/topic boundaries, using
embedding similarity between consecutive sentences to detect topic shifts)
was the real alternative, and remains the natural next step — deferred
because it requires embedding at chunk-boundary-decision time (extra
latency and complexity) for a quality improvement that wasn't the MVP's
priority.
