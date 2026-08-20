# AI / RAG Questions

**Q: Explain RAG in the context of this specific project.**
Instead of asking Claude to answer from its training data, the app first
finds the chunks of the uploaded document(s) most semantically similar to
the question (via embedding + FAISS search), then puts only those chunks in
the prompt and instructs the model to answer strictly from them. This turns
"does the model happen to know this" into "did we retrieve the right
passage," which is both more accurate for private/internal content and
lets the answer be checked against a real source.

**Q: Why chunk before embedding — why not embed the whole document?**
A single embedding for a whole document is an average of everything it
discusses — a question about one paragraph produces a diluted match against
that averaged vector. Chunking means each vector represents one narrow
piece of content, so similarity search can find the specific relevant
passage instead of just "this document talks about lots of things
generally." Full reasoning: [chunking.md](../learning/chunking.md).

**Q: Why fixed-size chunking instead of something smarter?**
Deterministic, dependency-free, and fast — no extra model call needed to
decide where boundaries go. It was a genuine trade-off for this MVP: chunk
quality was not the bottleneck being tested, and `ChunkingService` has a
stable contract (`list[Chunk]`) specifically so a semantic chunker could
replace it later without touching anything downstream. See
[ADR-0003](../decisions/0003-fixed-size-chunking.md) for what's given up
(sentence/table/code-block boundaries aren't respected) and how semantic
chunking would work instead.

**Q: How do you know retrieval is actually finding the right thing?**
`rag/tests/test_embedding_pipeline.py` embeds two chunks about unrelated
topics with the real FastEmbed model, embeds a query relevant to only one
of them, and asserts FAISS returns the relevant chunk first with a higher
score — a real semantic-retrieval assertion, not a plumbing check.

**Q: Why must documents and queries use the same embedding model?**
Similarity search only means something if both vectors were produced by the
same learned mapping from text to vector space — comparing vectors from two
different models (or even two checkpoints of the same model) is comparing
numbers with no shared meaning. `EmbeddingService` is the single place
embeddings happen for exactly this reason — both `embed_documents()` and
`embed_query()` go through the same loaded model instance. One subtlety:
BGE models are trained asymmetrically, so documents use `passage_embed()`
and queries use `query_embed()` — different calls, same underlying model
and vector space. Full explanation: [embeddings.md](../learning/embeddings.md).

**Q: How do you prevent hallucination? Do you guarantee it?**
No guarantee — the honest claim is "grounded generation with independent
verification," not "hallucination-proof." Three layers: (1) the system
prompt instructs context-only answers and explicit "I don't know" when the
context is insufficient; (2) the model architecturally never sees a
question without first going through retrieval — there's no code path for
an ungrounded answer; (3) `validate_answer()` independently checks every
cited `chunk_id` against what was actually retrieved for that query and
drops anything that doesn't match, rather than trusting the model's
compliance with the prompt. Layer 3 is the one that doesn't rely on the
model behaving — full reasoning: [prompt-engineering.md](../prompt-engineering.md).

**Q: What happens if the model cites a chunk it wasn't given?**
`validate_answer()` filters it out before it reaches the client and counts
it in `dropped_unverifiable_sources`. This is covered by a real test
(`test_prompt.py::test_drops_a_cited_chunk_id_that_was_never_retrieved`)
that hand-builds an `LLMResponse` with a fabricated `chunk_id` and asserts
it's dropped.

**Q: How is the structured output (answer + sources) enforced?**
Two layers: the Anthropic API call itself requests `output_config.format`
with a JSON Schema, which constrains what the model can return at the API
level (no prose wrapper, no markdown fences); a Pydantic model
(`AnswerModel`) then re-validates the parsed JSON on the application side,
as defense in depth against the API-level contract ever changing or being
insufficient (it guarantees shape, not that a `chunk_id` is real — that's
what the grounding check is for).

**Q: What's the actual limitation of this RAG setup you'd fix first?**
Chunking has no semantic or structural awareness — a chunk boundary can
split a sentence, a table row, or a list item, and there's no signal
preserved about document structure (which section a chunk came from).
That's the most direct lever on answer quality, ahead of anything about the
LLM call itself.
