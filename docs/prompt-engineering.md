# Prompt Engineering — RAG Answer Generation

This documents the design of the single prompt used in this pipeline: the
grounded question-answering prompt in `rag/services/prompt.py`, sent by
`rag/services/llm.py`.

## Role / instruction design

The system prompt (`SYSTEM_PROMPT`) opens by naming the role narrowly —
"a knowledge assistant for an internal enterprise knowledge base" — rather
than a generic "helpful assistant." This matters because the constraints
that follow (context-only answers, explicit "I don't know") only make sense
in light of *why* the assistant exists: it's answering from a specific,
bounded knowledge base, not from general knowledge.

The five numbered rules are deliberately short, stated once, and each says
what to do rather than only what not to do (rule 2 says say so explicitly,
not just don't guess). Per current Claude model behavior, instructions are
followed closely and literally — there's no need for `CRITICAL:` / `MUST`
emphasis to get the model's attention here; plain, specific instructions are
enough, and over-emphasizing risks over-triggering on the wrong parts of the
rule (e.g. refusing to answer things it actually could answer from context).

## Context injection

`build_user_prompt()` puts retrieved context *before* the question, each
chunk tagged with its `chunk_id` and source `document`:

```
[chunk_id: <id> | document: <filename>]
<chunk text>
```

Putting the machine-readable chunk_id directly in-line with the text it
labels (rather than in a separate list) means the model doesn't have to
cross-reference two different sections to know which chunk it's reading —
the citation key travels with the content.

If retrieval returns nothing, the context block explicitly says so
(`"(No relevant context was found in the knowledge base.)"`) rather than
being empty or omitted — an empty context section could be read as "there's
no context to follow" rather than "there is definitely no relevant
information," and the two should produce different behavior (the second
should always produce "I don't know").

## User query handling

The question is passed through unmodified, after the context block, with a
final line re-stating the grounding constraint immediately before the model
answers ("Respond with an answer grounded strictly in the context above.").
This repetition is intentional: it's the last thing the model reads before
generating, right where it has the most influence on the immediate
response, distinct from the system-level rules that apply to behavior in
general.

## Grounding and hallucination prevention

Three layers work together, deliberately overlapping rather than relying on
any single one:

1. **Prompt-level instruction.** Rules 1–3 and 5 in the system prompt
   directly instruct context-only answers and prohibit fabricating a
   chunk_id. This is necessary but not sufficient — an instruction is a
   strong bias, not a hard guarantee.
2. **Retrieval-first architecture.** The model is never given a chance to
   answer from unbounded knowledge — it is only ever shown the top-`k`
   retrieved chunks and the question. There is no code path where the LLM
   is asked a question without first going through
   `VectorStore.search()`.
3. **Post-hoc grounding verification.** `validate_answer()` in
   `rag/services/prompt.py` cross-checks every `chunk_id` the model cited
   in `sources` against the set of `chunk_id`s that were actually retrieved
   for this query, and silently drops any source that doesn't match. This
   is the layer that doesn't trust the model's compliance with rule 5 — it
   verifies it. A citation to a chunk that was never shown to the model is
   definitionally either fabricated or a formatting mistake, and either way
   it shouldn't be presented to the user as a real source.

Explicit "I don't know" handling (rule 2) is the other half of hallucination
prevention: a model that has been trained to always produce a confident
answer will, under pressure, invent one. Giving it explicit permission and
instruction to say the context is insufficient removes that pressure.

## Structured output strategy

The response shape is enforced two ways, not one:

1. **API-level schema enforcement.** `AnthropicLLMProvider` requests
   `output_config.format` with a JSON Schema
   (`{"answer": str, "sources": [{"document": str, "chunk_id": str}]}`,
   `additionalProperties: false`) rather than asking for JSON in prose and
   hoping. This is a Claude API feature that constrains the response format
   itself — the model cannot return prose-wrapped JSON, markdown code
   fences, or an extra explanatory paragraph before the JSON, because the
   API guarantees the returned text parses against the schema.
2. **Application-level parsing and validation.** `AnswerModel` (a Pydantic
   model in `rag/services/prompt.py`) re-validates the parsed JSON on the
   application side. This is deliberate defense in depth, not redundancy:
   API-level schema enforcement guarantees *shape*, not semantic
   correctness (e.g. it can't verify a `chunk_id` is real) — that's what
   `validate_answer()`'s grounding check is for. This also means the
   contract at the Python layer (`AnswerModel`) doesn't silently depend on
   the API call underneath it never changing.

`output_config.format` is intentionally not combined with citations
(Anthropic's separate `citations` content-block feature) — the two are
mutually incompatible on the API, and this pipeline's own
`{"document", "chunk_id"}` source format is a simpler, purpose-built
alternative for this MVP's needs.

## Failure handling when the model doesn't comply with the format

Even with schema enforcement, failure is handled explicitly rather than
assumed away:

- **`stop_reason == "refusal"`** — the model's safety classifiers declined
  to answer. `AnthropicLLMProvider.generate_structured_answer()` raises
  `LLMOutputError` rather than trying to parse `response.content`, since a
  refusal is not accompanied by a schema-shaped answer.
- **No text content in the response** — defensive check in case a future
  response shape omits a text block; raises `LLMOutputError` rather than
  crashing on a `None`.
- **JSON decode failure** — belt-and-suspenders in case schema enforcement
  is bypassed or a provider is later swapped in without equivalent
  guarantees; raises `LLMOutputError` with the underlying parse error
  rather than propagating a raw `JSONDecodeError` up through unrelated
  layers.
- **Pydantic validation failure** (`validate_answer()`) — the JSON parsed
  but didn't match the expected field types/shape; raised as a `ValueError`
  with the Pydantic error detail.

All of these are exceptions the query view (`rag/views.py`) is expected to
catch and turn into a clean `502`/`500`-style API error rather than letting
a raw exception or a malformed response reach the client — see
`QueryView` in `rag/views.py` for where that boundary is.
