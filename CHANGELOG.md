# Changelog

Each entry explains what changed, why, what problem it solved, what
alternatives were considered, and what was learned — not a bare commit
list. Dated by when the work was done.

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
