# System Overview

A small enterprise-knowledge RAG (retrieval-augmented generation) platform:
upload a document, ask a question, get an answer grounded in — and cited
from — that document.

## Components

| Component | Technology | Responsibility |
|---|---|---|
| Frontend | React + Vite | Upload UI, document list, question box, answer + sources display |
| API | Django + Django REST Framework | HTTP boundary: validation, status codes, orchestration entry points |
| Structured data store | PostgreSQL | `Document` bookkeeping rows (filename, status, chunk/char counts) |
| Text extraction | `rag/services/extractors.py` | File bytes → raw text, one extractor per supported format |
| Chunking | `rag/services/chunking.py` | Raw text → fixed-size overlapping chunks |
| Embeddings | FastEmbed (`rag/services/embedding.py`) | Chunk text / query text → 384-dim vectors, same model for both |
| Vector index | FAISS (`rag/services/vector_store.py`) | Nearest-neighbor search over chunk embeddings, persisted to disk |
| Grounded prompting | `rag/services/prompt.py` | Builds the LLM prompt from retrieved chunks; validates the model's citations against what was actually retrieved |
| LLM | Anthropic Claude, behind `LLMProvider` (`rag/services/llm.py`) | Generates a structured, schema-shaped answer from the grounded prompt |
| Orchestration | `rag/services/pipeline.py` | The only place that wires the above services together into the two end-to-end flows |

Each service in `rag/services/` has a single, narrow responsibility and no
knowledge of the others beyond what it's explicitly passed — see
[component-architecture.md](./component-architecture.md) for the module
boundaries and why they're drawn where they are, and each `docs/decisions/`
ADR for why each technology was chosen.

## The two request flows

1. **Ingestion** — upload a document once; it's extracted, cleaned,
   chunked, embedded, and indexed.
2. **Query** — ask a question any number of times; it's embedded, matched
   against the index, and answered strictly from the retrieved chunks.

Full step-by-step detail for both is in [data-flow.md](./data-flow.md).

## What this system is not

This is a single-tenant, single-process MVP, not a production deployment:
no auth/RBAC, no multi-tenancy, one FAISS index shared by all documents, no
background job queue (ingestion runs synchronously inside the HTTP
request), and no cloud infrastructure. See
[deployment-architecture.md](./deployment-architecture.md) for what's
actually running today versus what a production deployment would add.
