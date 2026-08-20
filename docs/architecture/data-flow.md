# Data Flow

Both flows are orchestrated end-to-end by `rag/services/pipeline.py` — views
call exactly one pipeline function each and otherwise stay thin.

## Ingestion flow

`POST /api/documents/upload` (multipart file) → `DocumentUploadView` →
`run_ingestion_pipeline(file_bytes, filename)`:

```
1. IngestionService.ingest(file_bytes, filename)
   - get_extractor(filename) picks the TextExtractor for the file's
     extension — TxtExtractor or PdfExtractor today (raises
     UnsupportedFileTypeError if no extractor is registered for the
     extension — the view maps this to 400)
   - extractor.extract() decodes/parses raw bytes to text (raises
     ExtractionError for a file whose extension is supported but whose
     content isn't parseable — corrupt/empty PDF — also mapped to 400;
     see ADR-0007)
   - extractor.extract_metadata() returns extractor-specific metadata
     (empty for .txt; {"page_count": N} for .pdf)
   - clean_text() collapses whitespace noise, strips control chars
   - assigns a UUID document_id
   → IngestedDocument(document_id, filename, text, char_count, metadata)

2. ChunkingService.chunk(document_id, filename, text)
   → list[Chunk], fixed-size windows with overlap (see ADR-0003)
   - if the document produced zero chunks (e.g. empty/whitespace-only
     file), the pipeline stops here and records a Document row with
     status=FAILED and an explanatory error_message — this is NOT an
     exception path, it's a normal, expected outcome the frontend surfaces
     as a failed upload, not a crash

3. EmbeddingService.embed_documents(chunks)
   → np.ndarray of shape (n_chunks, 384), via FastEmbed's passage_embed()

4. FaissVectorStore.add(chunks, embeddings)
   - assigns each chunk a monotonically increasing integer ID
   - adds vectors to the FAISS index under those IDs
   - writes chunk text + metadata to the JSON sidecar under the same IDs
   - persists both to disk immediately (no separate "flush" step)

5. Document.objects.create(...) — status=READY, chunk_count, char_count,
   page_count (from step 1's metadata; null for .txt)
```

The view returns the serialized `Document` row (`201`) regardless of
READY/FAILED status — a failed extraction is a valid, informative API
response, not a server error.

## Query flow

`POST /api/query` (`{"question": "..."}`) → `QueryView` →
`run_query_pipeline(question)`:

```
1. EmbeddingService.embed_query(question)
   → np.ndarray of shape (384,), via FastEmbed's query_embed()
   (the asymmetric counterpart to embed_documents() — see
   docs/learning/embeddings.md for why this matters)

2. FaissVectorStore.search(query_vector, top_k=RAG_TOP_K)
   → list[SearchResult], each with chunk_id, filename, text, and a
   cosine-similarity score, ordered highest-similarity first

3. build_user_prompt(question, retrieved_chunks)
   → a single prompt string: retrieved chunks (each tagged with its
   chunk_id and source filename) followed by the question

4. AnthropicLLMProvider.generate_structured_answer(SYSTEM_PROMPT, user_prompt)
   → calls the Claude API with output_config.format set to a JSON Schema
   ({"answer": str, "sources": [{"document", "chunk_id"}]})
   → LLMResponse(answer, sources, stop_reason)
   (raises LLMOutputError for a refusal, missing text, bad JSON, or any
   Anthropic API-level failure — auth, rate limit, exhausted credits,
   network error — all normalized to the same exception; the view maps
   this to 502)

5. validate_answer(llm_response, retrieved_chunks)
   - re-validates the JSON shape with a Pydantic model (defense in depth
     on top of the API's own schema enforcement)
   - drops any cited chunk_id that wasn't actually in this query's
     retrieved set — a citation to a chunk never shown to the model is
     either fabricated or a formatting mistake, either way not shown to
     the user as a real source
   → ValidatedAnswer(answer, sources, dropped_unverifiable_sources)
```

The view returns `{"answer": ..., "sources": [...]}` (`200`). If retrieval
found nothing relevant, step 3's context block says so explicitly
("No relevant context was found in the knowledge base"), and the system
prompt instructs the model to say it doesn't know rather than guess — see
[prompt-engineering.md](../prompt-engineering.md) for the full grounding
strategy.

## Error paths, end to end

| Failure | Where | HTTP status |
|---|---|---|
| Unsupported file extension | `IngestionService.ingest` → `UnsupportedFileTypeError` | 400 |
| Corrupt/empty PDF (or any file whose extension is supported but content isn't parseable) | `PdfExtractor.extract` → `ExtractionError` | 400 |
| Missing `file` / blank `question` | Serializer validation | 400 |
| No extractable text after cleaning | Pipeline returns a `FAILED` `Document`, not an exception | 201 (document status = `failed`) |
| Model refusal, malformed output, or any Anthropic API failure | `LLMOutputError` | 502 |
| `ANTHROPIC_API_KEY` not configured | `RuntimeError` from `get_llm_provider()` | 503 |
