# ADR-0008: CI runs deterministically, with no dependency on Anthropic credentials

**Status:** Accepted

## Context

This MVP is now frozen from a product-feature perspective (see the
2026-08-20 CHANGELOG entry). The remaining infrastructure gap is that
nothing verifies the repository automatically on push/PR — verification has
been "run the commands from the README by hand." Adding GitHub Actions CI
closes that gap.

The obvious risk: this project's core feature (`/api/query`) calls the
Anthropic API. A CI pipeline that requires a real `ANTHROPIC_API_KEY` with
usable credits would mean every contributor's push either needs a shared
paid credential (a real secret to leak, and a real cost per run) or CI stays
red without one. Neither is acceptable for a demonstrable MVP meant to run
in a generic GitHub repository.

## Decision

CI backend tests run with **no `ANTHROPIC_API_KEY` set at all** — not a real
key, not a fake placeholder.

This works without any special-casing because [ADR-0005](./0005-llm-provider-abstraction.md)
already put a seam at `get_llm_provider()`. Every test that exercises the
query path patches `rag.services.pipeline.get_llm_provider` (see
`rag/tests/test_api.py`) rather than letting a real `AnthropicLLMProvider`
get constructed. `anthropic.Anthropic()` is never instantiated during
`manage.py test`, so there is nothing for a missing key to break — the same
`RuntimeError` path that guards the missing-key case in production
(`rag/services/llm.py`) is itself exercised via a mock
(`test_missing_api_key_returns_503_not_a_stack_trace`), not by actually
removing an environment variable and hoping.

`manage.py check`, the migration-consistency check, and the full test suite
therefore need only disposable, CI-local values: a throwaway
`DJANGO_SECRET_KEY` and a Postgres service container with CI-only
credentials (`ci_test_user` / `ci_test_password` / `ci_test_db`), created
fresh for each run and discarded with it.

## Rationale

- **Determinism.** A CI run's pass/fail depends only on code, never on
  external API availability, quota, or network flakiness to a paid
  third-party service.
- **No secret to manage.** There is no Anthropic credential in GitHub
  Actions secrets, so there is nothing scoped to this repo that could leak
  through a workflow log, a malicious PR from a fork, or a misconfigured
  `pull_request_target` trigger.
- **Honest about what CI does and doesn't prove.** CI proves retrieval
  (chunking, FastEmbed embeddings, FAISS search — all real, no mocking),
  the API contract, and grounding-validation logic. It does not prove live
  Claude response quality — that already has a documented, narrower
  limitation in the README ("No live-LLM verification in this
  environment"). CI doesn't change that limitation; it just doesn't
  pretend to solve it either.
- **This is CI, not CD.** No deployment step exists yet, so there is no
  pipeline stage where a real key would even be needed. If/when a
  deployment pipeline is added, a real `ANTHROPIC_API_KEY` belongs there —
  scoped to that job, sourced from GitHub Actions secrets — not in the
  test-verification workflow.

## Consequences

- Anyone can fork this repository and get a fully green CI run with zero
  setup — no key to request, no credits to spend.
- The embedding step in `rag/tests/test_embedding_pipeline.py` still
  downloads the real FastEmbed model from Hugging Face Hub on a cold cache
  (no credentials required, but it is a real network dependency and the
  slowest part of the suite, roughly 20s uncached). This is a pre-existing
  property of the local test suite, not something CI introduces — accepted
  as-is rather than mocked, to keep testing the real embedding/retrieval
  path end to end.
- If a future change makes any test path construct `AnthropicLLMProvider`
  for real (rather than mocking `get_llm_provider`), CI will fail loudly
  with the same `RuntimeError` a developer would see locally without a
  `.env` — not a silent skip. That is the intended failure mode: it means
  the mocking boundary moved and needs to be re-established, not papered
  over with a fake key.

## Alternatives considered

- **A fake/placeholder `ANTHROPIC_API_KEY` in CI** (e.g.
  `sk-ant-ci-placeholder`) — would satisfy the `if not
  os.environ.get("ANTHROPIC_API_KEY")` check in `AnthropicLLMProvider`, but
  every current test path avoids constructing that class anyway, so the
  placeholder would be pure noise: a fake credential-shaped string sitting
  in a workflow file with no code path that reads it. Leaving it unset is
  more honest and easier to verify (`git grep` for `ANTHROPIC` in the
  workflow finds nothing to argue about).
- **Skipping LLM-path tests in CI** — rejected; those tests
  (`test_successful_query_returns_grounded_answer_and_sources`, grounding
  validation, the 503 mapping) are exactly the tests that most need to run
  on every push. They already don't need a real key.
