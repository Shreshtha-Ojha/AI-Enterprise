# ADR-0002: FastEmbed for embeddings

**Status:** Accepted

## Context

The RAG pipeline needs to turn chunk text and user questions into vectors in
a shared semantic space (see [embeddings.md](../learning/embeddings.md) for
the underlying concept). Something has to produce those vectors.

## How this was actually decided

FastEmbed was specified upfront in the task instructions that bootstrapped
this project ("FastEmbed embeddings" was listed as a required component),
not selected after comparing it against alternatives (e.g. `sentence-transformers`,
OpenAI/Anthropic embedding APIs, `instructor-xl`). The rationale below is
why the choice holds up, not the original decision process.

## Decision

Use FastEmbed (`BAAI/bge-small-en-v1.5`, 384 dimensions) as the single
embedding provider, wrapped in `EmbeddingService`
(`rag/services/embedding.py`).

## Rationale (why this holds up)

- **Runs locally, no API key, no per-call cost.** Embedding is on the hot
  path for every upload and every query; a local ONNX model means no
  network round-trip and no dependency on a second provider's uptime or
  billing, independent of the LLM call.
- **Small and fast enough for a single-process dev deployment.** `bge-small`
  is a deliberately compact model (384-dim output) — good enough retrieval
  quality for this project's scope without the latency or memory footprint
  of a larger embedding model.
- **One model, one place.** `EmbeddingService` is the only module that
  imports FastEmbed; `embed_documents()` and `embed_query()` both go through
  the same loaded instance, which is what makes it safe to compare document
  and query vectors at all (see embeddings.md's "why documents and queries
  must share the same embedding space" section — this is a correctness
  requirement, not a style preference).
- **Loaded once, as a process-wide singleton** (`get_embedding_service()`),
  because constructing it loads an ONNX model from disk — too expensive to
  redo per request.

## Consequences

- Swapping the embedding model means changing `RAG_EMBEDDING_MODEL` (or the
  `EmbeddingService` internals) and **re-embedding every existing chunk** —
  vectors from two different models are not comparable, so a model change is
  a full reindex, not a config toggle applied retroactively.
- Embedding quality is bounded by what a small local model can do; a larger
  hosted embedding model would likely improve retrieval on harder queries at
  the cost of latency, cost, and an external dependency.

## Alternatives considered

Not seriously, per "How this was actually decided" above. A hosted
embedding API (OpenAI, Voyage, Anthropic) was the most plausible
alternative in hindsight — better retrieval quality, but it would tie
ingestion and every query to a second billed external API, on top of the
LLM call already required for generation.
