# Roadmap

Not commitments or timelines — a record of the natural next increments,
ordered roughly by how directly they'd improve the MVP versus how much new
architecture they'd require. See [docs/decisions](./decisions/) for why the
current choices were made and what each one gives up.

## Would directly improve answer quality, no new infrastructure

- **More document formats.** PDF and DOCX extractors behind the existing
  `TextExtractor` interface (`rag/services/extractors.py`) — see
  [ADR-0006](./decisions/0006-single-document-format.md).
- **Semantic chunking**, replacing fixed-size windows — see
  [ADR-0003](./decisions/0003-fixed-size-chunking.md) for the approach.
- **Per-document delete**, including removing its vectors from the FAISS
  sidecar (no delete endpoint exists today).

## Would require new infrastructure

- **pgvector**, replacing the FAISS + JSON-sidecar store — the single
  biggest change, and the one that unblocks horizontal scaling and
  multi-tenant filtering. See [ADR-0004](./decisions/0004-faiss-vector-store.md).
- **A background job queue** for ingestion, so large documents don't hold
  an HTTP request open for the full embedding duration.
- **Auth/multi-tenancy**, scoping documents and queries to a user or
  organization — additive to the current schema (an owner FK, a metadata
  filter in vector search), not a rewrite.

## Explicitly out of scope for now

Anything requiring cloud infrastructure, a deployment pipeline, or
production-scale traffic handling — see
[deployment-architecture.md](./architecture/deployment-architecture.md) for
what that would take and why none of it is built yet.
