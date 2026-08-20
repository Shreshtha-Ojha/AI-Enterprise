# Database Questions

**Q: What's actually in PostgreSQL, and what isn't?**
Only the `Document` model — `id` (UUID), `filename`, `uploaded_at`,
`char_count`, `chunk_count`, `page_count` (nullable, PDF only), `status`,
`error_message`. No chunk text, no embeddings. That data lives entirely in
the FAISS index and its JSON metadata sidecar on disk. See the `Document`
model's own docstring in `rag/models.py` for why this split was deliberate.

**Q: Why not store chunk text/embeddings in Postgres too?**
This phase's scope used FAISS as the vector store (see
[ADR-0004](../decisions/0004-faiss-vector-store.md)), and FAISS needs its
own persisted representation regardless — duplicating chunk text into
Postgres as well would mean maintaining two copies with no clear owner. The
honest trade-off this creates: Postgres and the FAISS sidecar are not
transactionally linked. A crash between "vectors written to FAISS" and
"`Document` row created" leaves orphaned vectors with no corresponding
`Document` — this is a real, currently-unhandled inconsistency window, not
a solved problem.

**Q: If you moved to pgvector, what would the schema look like?**
A `Chunk` model with a `document` FK to `Document`, a `text` field, and a
`vector` column (via `pgvector`'s Django field support), replacing the JSON
sidecar entirely. Retrieval becomes a single SQL query — an ORDER BY on
vector distance, optionally joined with a `WHERE document__owner_id = ...`
for tenant filtering — instead of a FAISS search followed by a Python-side
dictionary lookup for metadata.

**Q: Why UUID primary keys instead of auto-incrementing integers?**
`document_id` needs to be generated *before* the row is inserted — it's
used to build `chunk_id` values (`f"{document_id}:{index}"`) during
chunking, which happens before the `Document` row is created (chunking and
embedding can fail or the document can end up empty, in which case the row
still needs a stable, pre-assigned ID). A UUID can be generated client-side
in Python; an auto-incrementing integer PK is only known after the INSERT.

**Q: How would you test database-touching code without hitting a real
database for every test?**
Django's `TestCase` wraps each test in a transaction and rolls it back —
already used in `rag/tests/test_api.py`, so tests that create `Document`
rows don't need manual cleanup. Tests that don't touch the database at all
(`test_chunking.py`, `test_ingestion.py`, `test_prompt.py`,
`test_vector_store.py`) use Django's `SimpleTestCase`, which explicitly
forbids database access — a cheap guardrail that keeps pure-logic tests
from silently gaining a DB dependency over time.

**Q: What indexes exist, and what would you add at scale?**
`Document.Meta.ordering = ["-uploaded_at"]` drives the list view's default
order; Postgres doesn't need an explicit index for a table this size. At
real scale, an index on `uploaded_at` (for the list ordering) and on
`status` (if the UI ever filters by status) would be the first additions —
neither exists today because there's no evidence they're needed yet.
