# Component Architecture

## Backend module boundaries

```
rag/
├── models.py         Document — thin bookkeeping row, no chunk/embedding data
├── serializers.py     DRF request/response shapes + validation
├── views.py           HTTP boundary only: call a pipeline function, map
│                       its exceptions to status codes
├── urls.py             /api/documents/upload, /api/documents, /api/query
└── services/
    ├── extractors.py   file bytes -> raw text + metadata (one class per
    │                     format: TxtExtractor, PdfExtractor)
    ├── ingestion.py    raw text -> cleaned IngestedDocument
    ├── chunking.py     text -> list[Chunk] (pure function, no I/O)
    ├── embedding.py    Chunk[]/str -> np.ndarray (the only FastEmbed import)
    ├── vector_store.py FAISS index + JSON metadata sidecar
    ├── llm.py          LLMProvider interface + AnthropicLLMProvider
    ├── prompt.py        grounded-prompt construction + answer validation
    └── pipeline.py      orchestrates the above into the two request flows
```

### Why views stay thin

`rag/views.py` never imports FastEmbed, FAISS, or the Anthropic SDK — it
calls `run_ingestion_pipeline()` / `run_query_pipeline()` and translates the
small set of exceptions those functions can raise into HTTP responses. This
means the request/response contract (status codes, JSON shapes) is defined
in exactly one file, independent of how the pipeline itself is implemented.

### Why the pipeline is the only place services are wired together

Each service in `rag/services/` only depends on plain Python types
(`str`, `bytes`, `Chunk`, `np.ndarray`) as inputs/outputs — never on Django
request/response objects, and never on each other except where the data
naturally flows (e.g. `vector_store.py` depends on the `Chunk` dataclass
from `chunking.py`, not on the chunking service itself). `pipeline.py` is
the one module that imports all of them and calls them in order. This is
what makes each service independently testable (see `rag/tests/`) — a
chunking test doesn't need Django's test database or a running Postgres,
because `ChunkingService` doesn't know Django exists.

### Process-wide singletons

`EmbeddingService`, `FaissVectorStore`, and `AnthropicLLMProvider` are each
loaded once per process via a `get_*()` accessor guarded by a
`threading.Lock` (e.g. `get_embedding_service()`), not constructed per
request — each wraps something expensive to initialize (an ONNX model load,
a FAISS index read from disk, an SDK client). This is safe for a single
Django dev-server process; see
[deployment-architecture.md](./deployment-architecture.md) for what
changes with multiple worker processes.

## Frontend module boundaries

```
frontend/src/
├── api/
│   ├── client.js       fetch wrapper: joins base URL, parses JSON,
│   │                     distinguishes ApiError (server responded) from
│   │                     NetworkError (request never landed)
│   ├── documents.js     listDocuments(), uploadDocument(file)
│   └── query.js         askQuestion(question)
├── components/
│   ├── DocumentUpload.jsx   file picker, upload state, success/error message
│   ├── DocumentList.jsx     loading/error/empty states, per-document status badge
│   ├── QueryBox.jsx          question input, client-side blank-question check
│   ├── AnswerPanel.jsx       answer text + sources
│   └── SourceList.jsx        source list with an explicit empty state
└── App.jsx              owns all state (documents, query result, loading/error
                            flags), passes data + callbacks down
```

### Why `ApiError` / `NetworkError` are distinguished

`apiFetch()` (`api/client.js`) throws `NetworkError` when the `fetch()` call
itself fails (backend down, wrong port, CORS misconfiguration) and
`ApiError` when the backend responded but with a non-2xx status. Every
component that surfaces an error message (`App.jsx`, `DocumentUpload.jsx`)
handles both explicitly, so "the backend is unreachable" and "the backend
rejected this request" never collapse into the same generic message — the
first is a local dev/ops problem, the second is usually something the user
can act on (fix the input, pick a different file).

### Why there's no separate state-management library

All state (`documents`, `queryResult`, loading/error flags) lives in
`App.jsx` via `useState`/`useCallback` and flows down as props. The
component tree is two levels deep and nothing needs to be shared outside
it — Redux/Context would be pure overhead here.
