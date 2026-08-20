# ADR-0005: LLM provider behind an interface

**Status:** Accepted

## Context

The pipeline needs an LLM call to turn retrieved context + a question into a
grounded, structured answer. Something has to decide how that call is made
and how its output is parsed and validated.

## How this was actually decided

An LLM provider abstraction was specified as a required component in the
task instructions that bootstrapped this project ("LLM provider
abstraction" was listed explicitly). The specific choice of Anthropic as the
concrete implementation, and the shape of the `LLMProvider` interface
itself, were left to be worked out — the rationale below reflects that
implementation-level reasoning, not a claim that the abstraction itself was
independently arrived at.

## Decision

Define `LLMProvider` as an abstract base class with one method —
`generate_structured_answer(system_prompt, user_prompt) -> LLMResponse` — in
`rag/services/llm.py`. `AnthropicLLMProvider` is the only implementation.
Every other module (`rag/services/pipeline.py`, `rag/views.py`) depends only
on `LLMProvider` and `get_llm_provider()`, never on the `anthropic` SDK
directly.

## Rationale

- **The provider is genuinely swappable.** Adding a second provider (e.g.
  OpenAI, a local model server) means writing one new `LLMProvider`
  subclass and pointing `get_llm_provider()` at it — no changes to
  `pipeline.py`, `prompt.py`, or `views.py`.
- **The failure surface is centralized.** All Anthropic-specific error
  handling (refusals, malformed output, and — after a bug fix during this
  MVP pass — API-level failures like rate limits, auth errors, and
  exhausted credits) is caught inside `AnthropicLLMProvider` and normalized
  to `LLMOutputError`, a provider-agnostic exception the rest of the
  codebase already knows how to handle. Callers never need to know which
  SDK's exception types to catch.
- **Testability.** `get_llm_provider()` is the one seam that needs mocking
  to test the rest of the pipeline (retrieval, prompt construction,
  grounding validation, API response shaping) without a real API call — see
  `rag/tests/test_api.py`, which does exactly this.

## Consequences

- The interface is intentionally narrow (one method, one request/response
  shape) because this project has exactly one call pattern (grounded
  Q&A with structured output). A provider abstraction covering streaming,
  tool use, or multi-turn conversation would need a larger interface — not
  built here because nothing in this MVP needs it.
- `AnthropicLLMProvider` is a thin wrapper, not a generic "any LLM" adapter
  — it still encodes Anthropic-specific concepts (`output_config.format`,
  `stop_reason == "refusal"`). The abstraction boundary is the *call
  contract*, not "hide every provider-specific detail everywhere."

## Alternatives considered

A more generic multi-provider library (e.g. LiteLLM) was not used — for a
single provider, project-specific code with an explicit, minimal interface
is easier to reason about than a general-purpose abstraction layer built for
N providers this project doesn't currently need.
