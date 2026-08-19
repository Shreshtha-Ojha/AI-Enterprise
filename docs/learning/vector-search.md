# Vector Search

## What vector similarity search means conceptually

Once every chunk is represented as an embedding (see
`docs/learning/embeddings.md`), retrieval becomes: given a query vector,
find the `k` stored vectors closest to it. "Closest" here means highest
cosine similarity — the embeddings this pipeline uses are unit-length, so
cosine similarity reduces to a plain dot product (inner product) between
vectors.

The naive way to do this is to compute the similarity between the query and
*every* stored vector, then sort — exact, but linear in the number of
chunks. At a handful of documents that's instant. At millions of chunks it
becomes the bottleneck. Vector search libraries and databases exist to make
this fast at scale, either by still doing an exact scan but heavily
optimized (fine at this project's scale) or by using approximate
nearest-neighbor (ANN) indexing structures that trade a small amount of
recall for large speedups at scale.

## Why FAISS for this MVP

This pipeline uses FAISS (`faiss-cpu`) with `IndexFlatIP` — a **flat**
(exact, brute-force) index using inner product, wrapped in `IndexIDMap2` so
each vector can be added and retrieved with an explicit integer ID rather
than a positional index. See `rag/services/vector_store.py`.

FAISS was the right choice here because:

- **It runs entirely locally**, in-process, with no server to deploy or
  configure — no new infrastructure beyond what a `pip install` already
  brings. This matches the pipeline's other MVP choices: PostgreSQL is used
  for structural data, but nothing about this phase requires a vector-capable
  database.
- **Flat/exact search is simplest to reason about and debug.** At the scale
  of a handful of demo documents, an approximate index buys nothing — exact
  search over a few thousand vectors is already sub-millisecond.
- **It's a well-established, single-purpose library** with no data model of
  its own to fight — it stores vectors and IDs, nothing else, which keeps
  the separation between "vector similarity" and "everything else about a
  chunk" clean (this file's own metadata sidecar carries the rest).
- **The index persists to a plain file on disk** (`faiss.write_index` /
  `faiss.read_index`), so the pipeline survives a process restart without
  needing a running database service for the vector store specifically.

## Why a production system would likely move to pgvector or a dedicated vector DB

The choices above are exactly the ones that stop making sense past a
prototype:

- **Consistency and a single source of truth.** Right now, chunk text and
  metadata live in a JSON sidecar file next to the FAISS index
  (`metadata.json`), entirely separate from the PostgreSQL database that
  tracks `Document` rows. Nothing enforces that the two stay in sync — a
  failed write to one after succeeding on the other leaves them
  inconsistent, and there's no transaction spanning both. **pgvector** (a
  PostgreSQL extension that adds a vector column type and similarity search
  operators) puts embeddings in the same database, and often the same
  table, as the rest of the application data — one source of truth, real
  transactions, and vectors can be joined against other columns (e.g. an
  eventual `organization_id` for multi-tenant filtering) in a single query.
- **No built-in multi-process/multi-node story.** This pipeline's FAISS
  index is a singleton loaded into one Python process's memory, guarded by a
  lock; a second worker process would load its own separate copy from the
  same file, and nothing coordinates writes across processes beyond "last
  writer wins" on the sidecar file. A production deployment with multiple
  app servers or worker processes needs a shared, concurrent-safe store —
  which is what a database (or a dedicated vector DB service) provides for
  free.
- **No replication, backup, or access control** beyond whatever the
  filesystem/volume gives you — a database already has these operational
  concerns solved.
- **Filtering.** Real queries often need "search these vectors, but only
  within organization X" or "only documents uploaded after date Y." A flat
  FAISS index has no native concept of metadata filtering — you'd have to
  over-fetch and filter in Python. pgvector lets you combine a `WHERE`
  clause with the similarity search in one SQL query, using indexes on both.
- **Scale beyond memory.** A flat index keeps all vectors in RAM. Dedicated
  vector databases (or pgvector with an approximate index type like HNSW)
  are built to scale past what comfortably fits in one process's memory and
  to serve approximate search efficiently at that scale.

None of this is a knock on FAISS — it's still a reasonable choice for
prototyping, for embedded/offline use cases, or even in production behind a
service boundary that owns its own consistency story. It's just not the
right default once the application already has a relational database doing
the bookkeeping and needs that bookkeeping to stay consistent with the
vectors.
