# Changelog

Each entry explains what changed, why, what problem it solved, what
alternatives were considered, and what was learned — not a bare commit
list. Dated by when the work was done.

## 2026-08-20 — GitHub Actions CI

**What changed:** Added `.github/workflows/ci.yml`, running on every push
and pull request as two independent jobs:

- **`backend-tests`** — Poetry install (from `poetry.lock`), a disposable
  PostgreSQL 16 service container with CI-only credentials, `manage.py
  check`, `manage.py makemigrations --check --dry-run`, and the full
  `manage.py test rag` suite (68 tests).
- **`frontend-checks`** — `npm ci`, `npm run lint` (oxlint), `npm run
  build` (Vite).

No deployment step was added — this is CI, not CD, and the README/CHANGELOG
do not claim otherwise.

**No Anthropic credentials in CI.** `get_llm_provider()` (the seam from
[ADR-0005](./docs/decisions/0005-llm-provider-abstraction.md)) is mocked in
every test that touches the query path, so `ANTHROPIC_API_KEY` is left
unset entirely in CI — not a real key, not a placeholder. See the new
[ADR-0008](./docs/decisions/0008-ci-without-llm-credentials.md) for the
full reasoning, including why a fake placeholder key was considered and
rejected as noise.

**Verification performed before this entry was written:** ran the exact
commands the workflow runs, locally — `manage.py check`,
`makemigrations --check --dry-run`, and `manage.py test rag` (68/68 pass,
~23s, against a real local PostgreSQL 16 and the real FastEmbed model — no
mocking of retrieval), plus `npm ci`, `npm run lint` (exits 0; the one
existing `set-state-in-effect` warning in `App.jsx` is unchanged, per this
task's explicit instruction not to touch it), and `npm run build`. The
workflow YAML was parsed and validated for syntax. GitHub Actions itself
was **not** executed — this environment has no access to actually run a
workflow on GitHub, so nothing here claims a real Actions run passed.

**README updated** with a "Continuous Integration" section documenting what
each job checks, that live Claude generation is intentionally not
required, and the exact commands to reproduce CI locally.

## 2026-08-20 — Final audit and MVP freeze

**What changed:** A full-repository audit pass (code, security, API
contract, RAG pipeline, documentation) with no new product functionality —
this closes out active development on the MVP. Concrete changes:

- **Removed dead config.** `config/settings.py` had a `MAILERS = {...}`
  dictionary left over from bootstrapping. `MAILERS` is not a real Django
  setting (Django's actual setting is `EMAIL_BACKEND`); nothing in the
  codebase referenced it, and the project sends no email. It was inert,
  misleading dead code — removed rather than fixed, since nothing needs it.
- **Surfaced `page_count` in the frontend.** The API has returned
  `page_count` for PDF uploads since the previous pass, but `DocumentList.jsx`
  never displayed it — a real frontend/backend inconsistency where useful
  data the backend computed was invisible in the UI. One-line fix.
- **Fixed two stale documentation claims.** `docs/interview/database-questions.md`
  listed `Document`'s fields but was missing `page_count` (added in the
  prior PDF-support pass and never back-filled here); `docs/interview/backend-questions.md`'s
  API-design answer described `400`s only as "validation/unsupported-format,"
  not mentioning the `ExtractionError` path (corrupt/empty PDF) added in the
  same prior pass. Both corrected to match the actual current code.
- **Added one real-behavior test.** `get_extractor()` lowercases the file
  extension before matching (`rag/services/extractors.py`), so `REPORT.TXT`
  and `Report.Pdf` resolve correctly — this was true of the code but had no
  test asserting it. One test added
  (`test_extension_matching_is_case_insensitive`), not to inflate the count
  but because it's a real, previously-unverified code path.
- **README polish:** corrected the stale test count (67 → 68), added
  `npm run build` / `npm run lint` and `manage.py check` to the setup
  instructions so the README's own verification commands match what this
  audit actually ran.

**Security audit (no fixes needed — verified only):**

- `.env` is gitignored and not tracked; `.env.example` contains only
  placeholder values (`change-me`, `sk-ant-your-key-here`); `git grep` for
  API-key-shaped strings, AWS keys, and PEM private key headers across all
  tracked files (excluding lockfiles) found nothing.
- `DJANGO_SECRET_KEY` and all `DB_*` credentials are `required=True`
  environment reads (`config/settings.py`) — no hardcoded fallback.
- `CORS_ALLOWED_ORIGINS` is an explicit allowlist (no wildcard, no
  `CORS_ALLOW_ALL_ORIGINS`); the frontend sends no credentials, matching
  the comment already in `settings.py`.
- **Filename handling was specifically probed, not assumed safe.** Tested
  uploading a file with a 300-character filename and a filename containing
  path separators, directly against a live endpoint. Confirmed Django's own
  `UploadedFile.name` setter (`django/core/files/uploadedfile.py`) already
  calls `os.path.basename()` (blocking path traversal via filename) and
  truncates to 255 characters preserving the extension (matching
  `Document.filename`'s `max_length=255`) *before* the name ever reaches
  application code — so this was already safe by virtue of using Django's
  `UploadedFile`, not something this project's code had to implement
  itself. Verified by direct reproduction, not by reading the framework
  source and assuming.
- LLM errors: confirmed (already true from the prior pass, re-verified by
  reading `rag/services/llm.py`) that `AnthropicLLMProvider` never returns
  the raw SDK exception — only a fixed, generic message — while the real
  exception is logged server-side.
- Uploaded file bytes are never written to disk under a user-controlled
  path — the whole pipeline operates on in-memory `bytes` end to end; there
  is no filesystem write of upload content anywhere to escape.

**What was NOT changed:** Architecture, dependencies (beyond what the PDF
pass already added), API contract, chunking strategy, or any of the
already-honest documented limitations (no OCR, synchronous ingestion,
single-process FAISS, no auth/multi-tenancy/rate limiting, no document
deletion, FAISS/PostgreSQL consistency gap). This pass found a small,
genuine polish backlog, not a design problem — the architecture built
across the prior two passes held up under a full adversarial-ish audit
without needing structural changes.

**Test results:** 68 tests (67 → 68, the one case-insensitivity test
above), all passing. `manage.py check` clean. `manage.py makemigrations --check`
clean (no missing migrations). Frontend `npm run build` succeeds; `npm run lint`
produces one pre-existing warning (`App.jsx`'s `set-state-in-effect` rule on
the standard fetch-on-mount `useEffect` pattern) — reviewed and left as-is,
since it's React's own documented pattern for synchronizing with an
external system (data fetching), not a functional bug, and rewriting
working code to satisfy an overzealous lint rule isn't in scope for this
freeze.

**What was learned:** Verifying a security assumption by actually
reproducing the attack (a long/path-like filename against a live endpoint)
rather than just reading the code was worth doing — it would have been easy
to assume "Django models truncate silently" (false — Postgres raises
`DataError` on direct ORM use with an overlong string) and miss that the
real protection is one layer up, in `UploadedFile` itself, before that
code path is ever reached through the actual upload endpoint.

## 2026-08-20 — Add PDF ingestion support

**What changed:** Extended the ingestion layer to support `.pdf` uploads
alongside the existing `.txt` support, through the existing extractor
abstraction/registry (`rag/services/extractors.py`) — no changes to
chunking, embedding, vector storage, the pipeline orchestration, or the
API contract's shape beyond one new nullable field. Added `PdfExtractor`
(via `pypdf`), a new `ExtractionError` exception for files whose extension
is supported but whose content isn't a parseable PDF, an
`extract_metadata()` hook on `TextExtractor` (used to report PDF page
count), and a nullable `Document.page_count` column. See
[ADR-0007](./docs/decisions/0007-pdf-extraction.md) for the full reasoning.

**Why:** [ADR-0006](./docs/decisions/0006-single-document-format.md) shipped
`.txt`-only deliberately, to prove the pipeline before taking on
format-specific extraction complexity, and named PDF support as the most
natural next increment — real knowledge-base documents are overwhelmingly
PDF or Word, not plain text. This closes that gap.

**What problem it solved:**

- **The extraction registry now has a second format, proving the
  abstraction actually extends the way ADR-0006 claimed it would.** Adding
  `PdfExtractor` required exactly one new subclass and one registry entry —
  nothing in `chunking.py`, `embedding.py`, `vector_store.py`, or
  `pipeline.py` changed.
- **Scanned/image-only PDFs are handled honestly, not silently.** `pypdf`
  reads a PDF's existing text layer only (no OCR). A scanned PDF extracts
  to empty text, which flows into the same "no extractable text after
  cleaning" path a whitespace-only `.txt` file already hit — recorded as
  `status=failed` with an explanatory message, not a crash and not a false
  success.
- **Corrupt/empty PDF content fails cleanly.** A new `ExtractionError`
  (distinct from `UnsupportedFileTypeError` — the extension is right, the
  content isn't parseable) maps to a `400` in `DocumentUploadView`, the
  same pattern already used for unsupported extensions.
- **18 new tests** (49 → 67): `PdfExtractor` unit tests (valid extraction,
  multi-page ordering, page-count metadata, blank/scanned PDF, empty bytes,
  corrupt bytes), `IngestionService` PDF tests (metadata flows through,
  extraction errors propagate), API-level tests (`201` with `page_count`,
  multi-page count, `.txt` has `null` page_count, corrupt/empty PDF → `400`,
  scanned PDF → `failed` not `500`, a full query round-trip against a
  PDF-derived document), and one real-FastEmbed/real-FAISS integration test
  proving a PDF-extracted chunk is retrieved semantically over an unrelated
  one — the same standard of "actually verify retrieval," not just
  "the plumbing runs," used for the existing `.txt` integration test. All
  tests use a hand-built, dependency-free PDF fixture
  (`rag/tests/pdf_fixtures.py`) — deterministic, no network, no external
  tool.
- **Frontend upload input now advertises both formats** (`accept=".txt,.pdf,..."`
  plus a visible "Supported formats: .txt, .pdf" hint) rather than silently
  accepting anything and letting the backend reject it after a round trip.

**What was NOT changed, on purpose:**

- **Chunking strategy.** Still fixed-500-char/50-overlap windows, applied
  identically to text from either format — PDF extraction didn't surface a
  concrete problem with it (extracted PDF text is just text once cleaned;
  chunking has no format awareness and doesn't need any). See
  [ADR-0007](./docs/decisions/0007-pdf-extraction.md) and
  [ADR-0003](./docs/decisions/0003-fixed-size-chunking.md).
- **No OCR.** Deliberately out of scope — a materially different capability
  (image processing) than "parse the text already embedded in a PDF."
- **No new infrastructure.** No LangChain, no Celery/Redis, no pgvector, no
  new auth surface — `pypdf` is the only new dependency, and it's a
  pure-Python PDF parser with no system binary requirement.

**Alternatives considered:** `pdfplumber` and `unstructured` were
considered and rejected as heavier than this project needs right now
(layout/table extraction, effectively a document-processing framework) —
see ADR-0007 for the full comparison, including why a single `(text,
metadata)` return from `extract()` (avoiding a second PDF parse for
metadata) was considered and deferred rather than adopted, since it isn't
a real cost yet at the file sizes this MVP handles synchronously.

**What was learned:** A hand-written, dependency-free PDF fixture builder
(raw object table + xref, no `reportlab`/`fpdf`) was worth the extra ~60
lines over pulling in a PDF-authoring library just for tests — it kept the
test suite's dependency footprint unchanged and made the fixture's exact
byte structure inspectable, which mattered once for debugging an
off-by-one in the xref offsets before the fixture parsed correctly.

## 2026-08-20 — MVP polish pass: fix LLM error handling, add tests, fill in documentation

**What changed:** Audited the existing Django/DRF + FastEmbed + FAISS + React
RAG pipeline (which was already functionally complete — ingestion, chunking,
embedding, retrieval, grounded prompting, and the frontend all worked),
fixed one real correctness bug, added a 49-test suite, and filled in the
architecture/decision/interview documentation that previously existed only
as empty stub files.

**Why:** The pipeline worked but wasn't demonstrable or defensible: zero
tests existed, the documentation directories were placeholders (`# Title`
and nothing else), and the README claimed the RAG layer was "planned for a
later phase" when it was already built. None of that reflects the actual
state of the code.

**What problem it solved:**

- **A real bug, not a hypothetical one.** `AnthropicLLMProvider.generate_structured_answer`
  only caught application-level failures (model refusal, missing text,
  invalid JSON) — it never caught the Anthropic SDK's own request-level
  exceptions (`anthropic.APIError` and its subclasses: auth failures, rate
  limits, exhausted credits, network errors). This was found by actually
  calling the live API, whose configured key turned out to have no usable
  credits — a real `anthropic.BadRequestError` propagated straight past the
  view's exception handling as an unhandled exception instead of the clean
  `502` the rest of the code already assumed it would get. Fixed by wrapping
  the API call in `except anthropic.APIError`, logging the real exception
  server-side (`logger.error(..., exc_info=True)`), and re-raising the
  existing `LLMOutputError` — no new exception type or view change needed,
  since `LLMOutputError` was already mapped to `502`. Re-verified against
  the live (still credit-exhausted) API after the fix: the same request now
  returns a clean error instead of a stack trace.
- **Zero test coverage.** Added 49 tests across `rag/tests/`: pure unit
  tests for chunking, extraction/cleaning, and prompt/grounding-validation
  logic; a real-FAISS integration suite using synthetic vectors to verify
  index/metadata alignment; a real-FastEmbed integration test that asserts
  actual semantic retrieval (a query is embedded and shown to retrieve the
  topically relevant chunk over an unrelated one, not just "the plumbing
  runs"); and API-level tests using DRF's `APIClient` against real views,
  a real (temp-directory-isolated) FAISS store, and real embeddings, with
  only the LLM provider boundary mocked. No live-Anthropic integration test
  was added — the account has no usable credits, and a mocked test standing
  in for one would misrepresent what was actually verified. The distinction
  is documented in `rag/tests/test_api.py`'s module docstring.
- **Stale/missing documentation.** `docs/architecture/*.md`,
  `docs/interview/*.md`, and `docs/decisions/` were empty placeholders;
  `README.md` and `pyproject.toml`'s description both still said the RAG
  layer was "planned" rather than built. Filled in system/data-flow/
  component/deployment architecture docs, six ADRs, and six interview-prep
  documents, all specific to this codebase (file/line references, not
  generic RAG explanations) — and cross-referenced against the two docs
  that were already excellent (`docs/learning/*.md`, `docs/prompt-engineering.md`)
  rather than duplicating their content.

**Alternatives considered:**

- For the LLM error fix: introducing a new, more granular exception
  hierarchy (e.g. separate exceptions for rate-limit vs. auth vs. network
  failures) was considered and rejected — nothing downstream currently
  needs to distinguish these cases differently (all map to the same `502`),
  so a single normalized `LLMOutputError` keeps the fix minimal and
  consistent with the existing design.
- For testing: mocking FastEmbed/FAISS everywhere (for speed and to avoid a
  model-download dependency) was considered and rejected in favor of a
  smaller number of real-model/real-index integration tests alongside fast
  mocked unit/API tests — the whole point of RAG-quality testing is
  verifying retrieval actually finds the right thing, which a mock can't
  demonstrate.
- For ADRs: writing them as if FastEmbed, FAISS, Django/DRF, and PostgreSQL
  were chosen after comparing alternatives was considered and rejected —
  those were specified upfront in the task instructions that originally
  bootstrapped this project. Each such ADR says so explicitly, and separates
  "why this holds up" (real, defensible reasoning) from "how it was actually
  decided" (given, not derived).

**What was learned:** The strongest signal that something is broken isn't
always in the code you're reading — it's in actually exercising the
external dependency. The LLM error-handling gap wasn't visible from
inspecting `llm.py` alone (the `except` clauses that existed all looked
reasonable); it only showed up by making a real API call and watching what
came back. Static review of well-documented, well-structured code did not
catch it; a genuinely-executed test on the live API's real current state
did.
