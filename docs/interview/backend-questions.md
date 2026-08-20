# Backend Questions

**Q: Why Django + DRF for this instead of something lighter like FastAPI?**
Given as a starting constraint for this project rather than chosen by
comparison — see [ADR-0001](../decisions/0001-django-drf-postgresql.md) for
the honest account. What holds up in hindsight: the ORM, migrations, and
admin site (`rag/admin.py`) meant zero time spent building bookkeeping
infrastructure, and DRF's serializers gave validation and response shaping
for free — appropriate for a project whose actual complexity is in the RAG
pipeline, not the web layer.

**Q: Walk me through your API design.**
Three endpoints: `POST /api/documents/upload` (multipart, runs the full
ingest pipeline synchronously, returns the created `Document`),
`GET /api/documents` (list, newest first), `POST /api/query`
(`{"question"}` → `{"answer", "sources"}`). Status codes are deliberately
specific: `400` for validation failures, an unsupported file extension, or
a file whose extension is supported but whose content doesn't parse (e.g.
a corrupt PDF); `201` for a successful upload (even if the resulting
document status is `failed` — that's a valid outcome, not a server error);
`502` for an LLM failure; `503` for missing API key configuration. See
[data-flow.md](../architecture/data-flow.md)'s error-path table.

**Q: Why does a failed document extraction return `201`, not an error
status?**
Because the *request* succeeded — the server did what was asked (tried to
ingest the file) and recorded an honest result. `Document.status` carries
the outcome; reserving `4xx`/`5xx` for cases where the request itself
couldn't be fulfilled (bad input, server fault) keeps the status code
meaningful. The frontend reads `document.status` and shows the failure
inline in the document list rather than treating it as an exceptional
error.

**Q: How are errors from the LLM call handled?**
This was a real bug I found and fixed during this pass: `AnthropicLLMProvider`
originally only caught application-level failures (a refusal, missing text,
invalid JSON) — not the Anthropic SDK's own request-level exceptions (auth
failure, rate limit, exhausted credits, network error). I reproduced this
for real against the live API (the configured key had no usable credits) and
watched an unhandled `anthropic.BadRequestError` propagate past the view's
exception handling. Fix: wrap the API call in `except anthropic.APIError`,
log the real exception server-side, and raise the same `LLMOutputError` the
rest of the code already maps to a `502` — no new exception type, no view
change needed. Verified against the live (still credit-exhausted) API after
the fix.

**Q: How do you keep secrets out of error responses?**
`AnthropicLLMProvider` never returns the raw SDK exception to the caller —
it logs the full detail with `logger.error(..., exc_info=True)` (visible
server-side only) and raises a generic, fixed message
("The LLM provider is currently unavailable...") that the view forwards as
the `502` body. `.env` holds all secrets, is gitignored, and `.env.example`
documents every variable without real values.

**Q: How is the request/response contract tested?**
`rag/tests/test_api.py` uses DRF's `APIClient` against real views, a real
(temp-directory-isolated) FAISS store, and real FastEmbed embeddings — only
the LLM provider is mocked, via `patch("rag.services.pipeline.get_llm_provider")`.
This means upload validation, document bookkeeping, list ordering, query
validation, grounding-filter behavior, and all three LLM-failure-to-status-code
mappings (success, `LLMOutputError` → 502, missing-key `RuntimeError` → 503)
are tested against real code paths, not mocks standing in for the parts that
matter.

**Q: What's missing from the API that a real product would need?**
Pagination on `GET /api/documents` (fine at demo scale, not at real scale),
authentication/authorization, rate limiting on `/api/query` (an unbounded
per-request LLM call is a real cost/abuse surface), and a way to delete a
document (there's currently no delete endpoint — removing a document's
vectors from the FAISS sidecar isn't implemented).
