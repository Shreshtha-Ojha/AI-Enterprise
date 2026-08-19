# Chunking

## Why chunking is required

Embedding models and LLM context windows both have practical limits, but the
deeper reason to chunk is retrieval precision, not just size. If you embed an
entire document as one vector, that vector is an average of everything the
document talks about — a question about one paragraph in a 50-page document
produces a weak, diluted match. Splitting a document into smaller chunks
before embedding means each vector represents a narrow, specific piece of
content, so similarity search can find the *relevant paragraph*, not just the
relevant document.

Chunking also controls what gets injected into the LLM's prompt at query
time: we want the smallest amount of text that still contains the answer, so
the model isn't reasoning over irrelevant surrounding content it has to
filter out itself.

## Why fixed-size chunking was chosen for the MVP

This pipeline chunks with a fixed character window (default 500 characters)
and a fixed overlap (default 50 characters) — see `ChunkingService` in
`rag/services/chunking.py`.

Fixed-size chunking was chosen over semantic chunking for this phase because:

- **It's deterministic and dependency-free.** No extra model call, no
  sentence/paragraph boundary detection, no tuning of similarity thresholds.
  Given the same input, you always get the same chunks.
- **It's fast and cheap.** Pure string slicing — no LLM or embedding call
  needed to *decide* where chunk boundaries go (only to embed the chunks
  afterward).
- **It's predictable in size**, which matters for embedding batch
  performance and for bounding how much context gets sent to the LLM per
  retrieved chunk.
- **It's "good enough" for a first working pipeline.** The goal of this MVP
  is a correct, observable end-to-end RAG flow, not chunking quality — that's
  an easy thing to swap out later without touching the rest of the pipeline
  (chunking is an isolated service with a stable output contract:
  `list[Chunk]`).

500 characters (~90–120 English words) is small enough to keep each chunk
topically coherent and large enough to usually contain a full thought. A 50
character overlap (10% of chunk size) is a light guard, not a strong one —
see limitations below.

## Why overlap exists

Fixed-size chunking cuts text at arbitrary character boundaries with no
awareness of sentences or ideas. Without overlap, a sentence that happens to
straddle a chunk boundary gets split in half, and *neither* resulting chunk
contains the complete thought — so a query about that sentence may fail to
match either chunk well, or match a chunk that only has half the context.

Overlap means the text right around each boundary appears in both the
preceding and following chunk, so a boundary-straddling idea is still
findable as a coherent unit in at least one chunk.

## Limitations of this approach

- **No semantic awareness.** A chunk boundary can fall in the middle of a
  sentence, a code block, a table row, or a list item. Overlap reduces the
  chance that this destroys retrievability, but does not guarantee a chunk
  is ever a complete, self-contained thought.
- **Uniform size regardless of content structure.** A dense technical
  paragraph and a heading followed by whitespace get the same 500-character
  treatment, even though they carry very different amounts of information
  per character.
- **Duplicated content across overlapping chunks** slightly inflates the
  index and can cause the same underlying passage to be retrieved twice
  (as two separate chunks) for a single query.
- **No structural signal preserved.** Headings, sections, and document
  hierarchy are flattened into character offsets; the chunker doesn't know
  "this chunk is under section 3.2."

## How semantic chunking could be added later

Semantic chunking splits text at natural boundaries — sentences, paragraphs,
or topic shifts — instead of fixed character counts. A common approach:

1. Split the document into sentences (or paragraphs).
2. Embed each sentence.
3. Walk through consecutive sentences and start a new chunk when the
   embedding similarity between consecutive sentences drops below a
   threshold (a topic shift), merging sentences into a chunk while
   similarity stays high.
4. Optionally cap chunk size as an upper bound, falling back to fixed-size
   splitting only when a semantic unit is unusually large.

Because `ChunkingService.chunk(document_id, filename, text) -> list[Chunk]`
is the only contract the rest of the pipeline depends on, a
`SemanticChunkingService` implementing the same signature could be dropped in
without changing the ingestion service, the embedding service, or the vector
store — only the object the pipeline constructs would change.
