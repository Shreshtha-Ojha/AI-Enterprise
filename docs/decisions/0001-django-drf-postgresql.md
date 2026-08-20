# ADR-0001: Django + DRF backend on PostgreSQL

**Status:** Accepted

## Context

The project needed a backend framework and a primary datastore for document
bookkeeping (filename, status, chunk/char counts) and, longer-term, any
structured application data.

## How this was actually decided

This was specified upfront, in the task instructions that bootstrapped this
project ("Django + DRF + PostgreSQL backend"), not chosen after comparing it
against alternatives (e.g. FastAPI + SQLAlchemy, Flask). The reasoning below
explains why the choice is a reasonable one for this project's shape — it is
retrospective justification for a given constraint, not the original
decision process.

## Decision

Use Django + Django REST Framework for the API layer, PostgreSQL as the
relational database.

## Rationale (why this holds up)

- **Django ships the boring parts.** ORM, migrations, the admin site (used
  as-is in `rag/admin.py` for inspecting `Document` rows during
  development), and a mature ecosystem — none of which this project needed
  to build itself.
- **DRF gives structured request/response handling for free.** Serializers
  (`rag/serializers.py`) provide input validation with predictable error
  shapes and output shaping, which is most of what a small JSON API needs.
- **PostgreSQL is a safe relational default.** It's what most teams run in
  production, it's what `pgvector` (see [ADR-0004](0004-faiss-vector-store.md))
  would extend if the vector store moved into the database later, and
  Docker Compose here (`docker-compose.yml`) makes local setup a single
  command.

## Consequences

- The `Document` model (`rag/models.py`) is deliberately thin — it is a
  listing/status record, not a copy of chunk text or embeddings (those live
  in the FAISS-backed store, see ADR-0004). This keeps Postgres's role
  narrow and unambiguous for this phase.
- Django's synchronous request/response model is a fine fit for this
  project's workload (a single ingestion or query call per request, no
  background job queue) — see
  [deployment-architecture.md](../architecture/deployment-architecture.md)
  for where that stops being true.

## Alternatives considered

Not seriously — see "How this was actually decided" above. FastAPI would
have been a reasonable alternative for a smaller, fully-async API surface,
but Django/DRF's batteries (admin, migrations, validation) outweighed that
for a project doing DB-backed bookkeeping alongside the RAG pipeline.
