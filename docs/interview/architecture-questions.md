# Architecture Questions

**Q: Walk me through what happens when a user uploads a document.**
`DocumentUploadView` validates the multipart request, then calls
`run_ingestion_pipeline()`. That function extracts text (format-specific
extractor), cleans it, chunks it (fixed 500-char windows, 50-char overlap),
embeds every chunk with FastEmbed, adds the vectors to the FAISS index with
their metadata, and writes a `Document` row to Postgres with the resulting
status. Full detail: [data-flow.md](../architecture/data-flow.md).

**Q: Why is the view so thin — why not just do this in the view?**
So the request/response contract (status codes, JSON shapes) lives in one
place, and the pipeline logic can be tested and reused without spinning up
a Django request/response cycle. Every service in `rag/services/` takes and
returns plain Python types, not Django objects — that's what makes them
independently unit-testable.

**Q: What's the actual module boundary between services — how strict is
it?**
Each service only imports what it needs and never reaches into a sibling
service's internals. `vector_store.py` imports the `Chunk` dataclass from
`chunking.py` (because it needs that shape), but never imports
`ChunkingService` itself. `pipeline.py` is the only module that imports
every service and calls them in sequence. See
[component-architecture.md](../architecture/component-architecture.md).

**Q: Why FAISS instead of pgvector, given you're already using Postgres?**
Given as a starting constraint for this phase, not chosen after comparing
alternatives — see [ADR-0004](../decisions/0004-faiss-vector-store.md) for
the honest account of that and the real trade-off it creates: two sources
of truth (a JSON sidecar file and the `Document` table) with nothing
transactionally linking them. pgvector is the natural next step precisely
because it would collapse that into one store.

**Q: How would this scale past a demo?**
The two real bottlenecks: (1) FAISS is single-process and in-memory — a
second app server wouldn't see the same index, so scaling out horizontally
needs a shared store (pgvector, or a dedicated vector DB); (2) ingestion
runs synchronously inside the HTTP request — a large document would hold a
worker for the full embedding duration, which argues for a background job
queue. Neither is implemented; see
[deployment-architecture.md](../architecture/deployment-architecture.md)
for the honest "not implemented" list.

**Q: What would break first under real load?**
Concurrent uploads writing to the same FAISS sidecar file — the store has
an in-process lock, but that only protects against races *within* one
process. Two Django worker processes writing at once is a real race the
current code does not protect against (there's no file lock, no
distributed lock). This is a genuine known gap, not something the current
implementation handles gracefully.

**Q: Why no authentication?**
Out of scope for this phase by explicit choice — the goal was a coherent,
demonstrable RAG pipeline, not a multi-tenant product. Adding it later means
an `owner`/`organization` FK on `Document`, a `user_id` (or similar) tag on
every vector's metadata, and a filter in `FaissVectorStore.search()` — the
metadata sidecar already carries arbitrary per-chunk fields, so the schema
change is additive, not a rewrite. The harder part is what pgvector would
make trivial (`WHERE`-clause filtering) and FAISS makes manual (filter
after over-fetching, or partition into per-tenant indices).
