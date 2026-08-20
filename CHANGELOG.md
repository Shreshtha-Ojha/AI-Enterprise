# Changelog

Each entry explains what changed, why, what problem it solved, what
alternatives were considered, and what was learned — not a bare commit
list. Dated by when the work was done.

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
