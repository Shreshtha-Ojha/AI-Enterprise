# Embeddings

## What an embedding is

An embedding is a fixed-length vector of numbers (in this pipeline, 384
floating-point numbers per chunk — the output size of the
`BAAI/bge-small-en-v1.5` model used by FastEmbed) that represents the
*meaning* of a piece of text, produced by a neural network trained
specifically to place semantically similar text near each other in that
vector space.

Two pieces of text with similar meaning — even if they share almost no words
in common ("a small domesticated feline" vs. "cats are pets") — end up as
vectors that point in a similar direction. Two pieces of text with unrelated
meaning end up pointing in very different directions, regardless of surface
word overlap.

## Why semantic similarity search works

Once text is represented as vectors in a shared space, "how similar are
these two pieces of text in meaning" becomes a geometry problem: measure the
angle (or distance) between their vectors. This pipeline uses cosine
similarity via inner product (`rag/services/vector_store.py`) — FastEmbed's
BGE models already output unit-length vectors, so the inner product of two
vectors *is* their cosine similarity, in `[-1, 1]`, with `1` meaning
"pointing in exactly the same direction" (near-identical meaning).

This is what makes retrieval-augmented generation possible: instead of doing
keyword matching (which fails when the user's wording doesn't match the
document's wording) or asking an LLM to read every document for every
question (too slow, too expensive, and larger than most context windows),
we precompute an embedding for every chunk once, and at query time we embed
just the question and find the chunks whose vectors are closest to it. This
turns "find the relevant information" into a fast nearest-neighbor search
instead of an exhaustive read.

## Why documents and queries must share the same embedding space

Similarity search is only meaningful if the numbers being compared were
produced by *the same mapping from text to vector space*. If document
chunks were embedded with one model and the user's query were embedded with
a different model (or even the same model family but a different
checkpoint/version), their vectors would live in unrelated coordinate
systems — a high dot product would mean nothing, because "pointing in the
same direction" is only meaningful within a single model's learned space.

This is why `EmbeddingService` (`rag/services/embedding.py`) is the single
place embeddings happen in this codebase: both `embed_documents()` (used
during ingestion) and `embed_query()` (used during retrieval) go through the
same loaded model instance, guaranteeing every vector in the index and every
query vector come from the same embedding space and can be meaningfully
compared.

One subtlety specific to this model family: `embed_documents()` uses
FastEmbed's `passage_embed()` and `embed_query()` uses `query_embed()`
rather than a single generic `embed()` call. BGE-family models are trained
*asymmetrically* — they apply a different internal prompt template to
"things being searched over" (passages) versus "the search request" (a
query) — but both still land in the same shared vector space by
construction. Using the matching method for each side is required to get
the model's intended behavior; using `embed()` for both would still produce
vectors in the same space, just not calibrated the way the model was trained
to be queried.
