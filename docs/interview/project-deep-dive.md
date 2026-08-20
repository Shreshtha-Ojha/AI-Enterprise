# Project Deep Dive

## 30-second pitch

An enterprise knowledge assistant: upload a `.txt` or `.pdf` document, ask a
question about it, get an answer that's grounded in — and cited from — the
actual document content, not the model's general knowledge. Django/DRF +
PostgreSQL backend, FastEmbed embeddings, a local FAISS vector index, Claude
for generation, React/Vite frontend. Built end-to-end by me as a single
project, not a tutorial clone.

## Walkthrough (what I'd say if asked to demo it)

1. Upload a `.txt` or `.pdf` file. The backend picks the right extractor for
   the extension (`rag/services/extractors.py`), extracts and cleans the
   text, splits it into ~500-character overlapping chunks, embeds every
   chunk with a local FastEmbed model, and adds the vectors to a FAISS index
   — all inside one request. The document shows up in the list with its
   status, chunk count, and (for PDFs) page count.
2. Ask a question. The backend embeds the question with the *same* model,
   finds the most similar chunks in FAISS, and builds a prompt that gives
   Claude only those chunks as context — with an explicit instruction to say
   "I don't know" rather than guess if the context doesn't answer the
   question.
3. Claude returns a structured JSON answer (enforced by the API's own JSON
   Schema output mode) with a list of cited chunk IDs. Before that reaches
   the user, the backend independently checks every cited `chunk_id` against
   the chunks that were actually retrieved for *this* query — any citation
   that doesn't match is dropped rather than trusted. The answer and
   verified sources render in the UI.

## What I'd highlight as the strongest engineering decisions

- **The grounding check is not just a prompt instruction.** The system
  prompt tells the model to only cite real chunk IDs, but `validate_answer()`
  (`rag/services/prompt.py`) doesn't trust that — it cross-checks every
  citation against the actual retrieved set server-side and silently drops
  anything that doesn't match. Three independent layers work together
  (prompt instruction, retrieval-first architecture, post-hoc verification)
  — see [prompt-engineering.md](../prompt-engineering.md).
- **The pipeline is a straight, testable chain of pure-ish services**
  (`extractors → ingestion → chunking → embedding → vector_store → prompt →
  llm`), each with a narrow, typed contract and no dependency on Django
  beyond what it strictly needs. `pipeline.py` is the only place they're
  wired together. This is why 67 tests cover the pipeline without needing a
  real Anthropic call for most of them.
- **Adding PDF support proved the extractor abstraction, not just used
  it.** `TextExtractor` + the `EXTRACTORS` registry existed from the
  `.txt`-only MVP specifically so a second format could be added without
  touching anything downstream — see
  [ADR-0007](../decisions/0007-pdf-extraction.md). Adding `PdfExtractor`
  really was one class + one registry entry; chunking, embedding, storage,
  and the API contract didn't change.
- **LLM failures are handled as a first-class case, not an afterthought.**
  During this MVP pass I found and fixed a real gap: the Anthropic SDK's own
  exceptions (auth failure, rate limit, exhausted credits) weren't being
  caught — only application-level failures like a refusal or malformed JSON
  were. A real API failure was reaching the client as an unhandled
  exception instead of a clean `502`. See the LLM-provider section below and
  [CHANGELOG.md](../../CHANGELOG.md).

## What I'd be upfront about as limitations

- `.txt` and `.pdf` are supported today; DOCX and other formats aren't yet
  — the extraction layer is designed to extend (one class + a registry
  entry per format), which is exactly how PDF support was added.
- PDF support has no OCR — it reads a PDF's existing text layer only, so a
  scanned/image-only PDF ingests as "no extractable text" rather than being
  silently accepted or silently failing.
- FAISS is a single-process, in-memory index with a JSON sidecar for
  metadata — it doesn't share state across multiple app server processes,
  and nothing keeps it transactionally consistent with the PostgreSQL
  `Document` table.
- No auth, no multi-tenancy, no rate limiting. Anyone who can reach the API
  can upload documents and query all of them.
- I could not verify the full query loop against a live Claude response
  during this pass — the configured API key had no usable credits. Retrieval
  is verified working end-to-end with real embeddings and real FAISS search;
  the LLM call itself is verified for its *failure* paths (which I could
  reproduce for real, against the real API), and for its *success* path only
  via a mocked provider that exercises the same JSON-parsing and grounding
  validation code a real response would go through.

## Likely follow-up questions and where to look

- "Why FAISS instead of a real vector DB?" → [ADR-0004](../decisions/0004-faiss-vector-store.md)
- "How do you stop the model from making things up?" → [prompt-engineering.md](../prompt-engineering.md)
- "How would you scale this?" → [deployment-architecture.md](../architecture/deployment-architecture.md)
- "What would you do differently / next?" → [ROADMAP.md](../ROADMAP.md)
