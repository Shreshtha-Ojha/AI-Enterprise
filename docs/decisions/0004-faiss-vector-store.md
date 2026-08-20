# ADR-0004: FAISS for the vector index (local, file-backed)

**Status:** Accepted

## Context

Retrieval needs a way to find the top-`k` chunks whose embeddings are
closest to a query embedding — see [vector-search.md](../learning/vector-search.md)
for the underlying concept.

## How this was actually decided

FAISS was specified upfront in the task instructions that bootstrapped this
project ("FAISS in-memory vector indexing" was listed as a required
component), not selected after comparing it against alternatives (pgvector,
a managed vector database, Postgres full-text search). The rationale below
is why the choice holds up for this phase, not the original decision
process.

## Decision

Use FAISS (`faiss-cpu`) with `IndexFlatIP` (exact, brute-force inner-product
search) wrapped in `IndexIDMap2`, persisted to a plain file on disk plus a
JSON metadata sidecar (`rag/services/vector_store.py`). One process-wide
singleton (`get_vector_store()`), guarded by a lock.

## Rationale (why this holds up)

- **No new infrastructure.** Runs in-process; nothing to deploy or
  configure beyond the `pip`/Poetry dependency already in place.
- **Flat/exact search is simple to reason about and debug** at this
  project's scale (a handful of demo documents) — an approximate index
  would trade correctness for a speedup this scale doesn't need.
- **Single-purpose, no data model of its own to fight.** FAISS stores
  vectors and integer IDs; the metadata sidecar carries everything else a
  search result needs to be useful (`document_id`, `filename`, `chunk_id`,
  `text`).
- **Survives a process restart** — the index and sidecar are written to
  disk (`faiss.write_index` / a JSON file), not held only in memory.

## Consequences (what this doesn't solve)

- **Two sources of truth.** Chunk text/metadata live in `metadata.json`,
  entirely separate from the `Document` rows in PostgreSQL. Nothing
  transactionally links them — a failure between "chunks embedded and
  indexed" and "Document row created" (or vice versa) can leave them out of
  sync. `run_ingestion_pipeline` creates the `Document` row *after* the
  vector store write, so a mid-pipeline crash leaves orphaned vectors with
  no corresponding `Document` record, rather than a `Document` pointing at
  missing vectors — the safer of the two failure directions, but neither
  side has a repair path today.
- **No multi-process story.** A second worker process loads its own copy of
  the index from the same file; concurrent writers are not coordinated
  beyond "last writer wins" on the sidecar file.
- **No metadata filtering** (e.g. "only this organization's documents") —
  everything in the index is searched.
- **Everything lives in memory**, bounded by what fits in one process.

## What would change in production

This is exactly what stops making sense past a prototype: **pgvector**
would put embeddings in the same PostgreSQL database as `Document` rows —
one source of truth, real transactions, and the ability to combine a `WHERE`
clause (e.g. tenant filtering) with similarity search in a single query.
Full reasoning in [vector-search.md](../learning/vector-search.md).

## Alternatives considered

Not seriously, per "How this was actually decided" above. pgvector is the
most plausible alternative in hindsight, given PostgreSQL is already the
system of record for `Document` metadata (see [ADR-0001](0001-django-drf-postgresql.md)).
