# Deployment Architecture

## What actually runs today

This project runs as local development processes only — there is no
deployed environment, no CI/CD, and no cloud infrastructure backing it.
Concretely:

- **Backend:** `python manage.py runserver` — Django's single-process,
  single-threaded (per-request) dev server.
- **Database:** PostgreSQL, either a local install or the single-container
  `docker-compose.yml` in the repo root (explicitly labeled in that file as
  "local development convenience only — not a deployment topology").
- **Vector store:** a FAISS index + JSON metadata sidecar on local disk
  (`data/vector_store/`, gitignored), loaded into the Django process's
  memory as a singleton (see [ADR-0004](../decisions/0004-faiss-vector-store.md)).
- **Frontend:** `npm run dev` — Vite's dev server with hot module reload,
  talking to the backend over `VITE_API_BASE_URL` (`http://localhost:8000`
  by default).
- **CORS:** scoped to the Vite dev server's origin(s) via
  `CORS_ALLOWED_ORIGINS`, not a wildcard — see `config/settings.py`.
- **Secrets:** a local `.env` file (gitignored; `.env.example` documents
  every variable), loaded via `python-dotenv`. No secrets manager, no
  environment-specific config beyond what `.env` provides.

## Known constraints of this setup

- **Ingestion and query both run synchronously inside the HTTP request.**
  A large document's embedding step, or a slow LLM call, blocks that
  request for its full duration. There is no background job queue — this
  was a deliberate scope decision (no Celery/Redis) to keep the MVP's
  moving parts to what the RAG flow actually needs, not a gap that was
  missed.
- **The FAISS index is single-process.** A second worker process would
  load its own copy from the same file; nothing coordinates concurrent
  writes beyond "last write wins" on the sidecar file (see ADR-0004).
- **`DEBUG=True` in local dev** means Django error pages can include
  tracebacks — acceptable for local development, and explicitly why
  `rag/services/llm.py` catches Anthropic SDK exceptions and re-raises a
  generic `LLMOutputError` rather than letting a raw provider exception
  (which could include request-specific detail) reach that error page or,
  in a `DEBUG=False` deployment, an uncontrolled 500.

## What a real deployment would add (not implemented)

Listed for honesty about scope, not as a promise of what exists:

- A WSGI/ASGI server (gunicorn/uvicorn) behind a reverse proxy, instead of
  the Django dev server.
- A managed PostgreSQL instance, with `pgvector` absorbing the FAISS
  index's job so vectors and `Document` rows share one transactional store
  across multiple app processes (see ADR-0004's "what would change in
  production").
- A background job queue for ingestion, so large-file embedding doesn't
  hold an HTTP request open.
- A secrets manager instead of a `.env` file, and environment-specific
  settings instead of one local settings module.
- Structured logging and basic observability (the current `logger.error(...)`
  call in `rag/services/llm.py` is the only structured logging in the
  codebase today).
- A built, statically-hosted frontend (`npm run build`) served from
  somewhere other than the Vite dev server, with `VITE_API_BASE_URL`
  pointed at a real backend origin.

None of this is implemented, and none of it is claimed as implemented
elsewhere in this repo's documentation.
