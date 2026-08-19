"""Local FAISS-backed vector store.

Deliberately self-contained: it knows nothing about Django models or
Postgres. It owns both the vectors (FAISS index) and the metadata needed to
turn a vector match back into something useful (a small JSON sidecar file),
so search() can return chunk text and document metadata directly without a
second lookup. See docs/learning/vector-search.md for why this is
appropriate for the MVP and what changes when this moves to pgvector.
"""

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

import faiss
import numpy as np
from django.conf import settings

from rag.services.chunking import Chunk

_METADATA_FILENAME = "metadata.json"
_INDEX_FILENAME = "faiss.index"


@dataclass(frozen=True)
class SearchResult:
    document_id: str
    filename: str
    chunk_id: str
    chunk_index: int
    text: str
    score: float  # cosine similarity, higher = more similar


class FaissVectorStore:
    def __init__(self, dimension: int, store_dir: Path | None = None):
        self._dimension = dimension
        self._store_dir = Path(store_dir or settings.RAG_VECTOR_STORE_DIR)
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._store_dir / _INDEX_FILENAME
        self._metadata_path = self._store_dir / _METADATA_FILENAME
        self._lock = threading.Lock()
        self._index, self._metadata, self._next_id = self._load()

    def _load(self):
        if self._index_path.exists() and self._metadata_path.exists():
            index = faiss.read_index(str(self._index_path))
            metadata = json.loads(self._metadata_path.read_text())
            metadata = {int(k): v for k, v in metadata.items()}
            next_id = max(metadata.keys(), default=-1) + 1
            return index, metadata, next_id
        index = faiss.IndexIDMap2(faiss.IndexFlatIP(self._dimension))
        return index, {}, 0

    def _save(self):
        faiss.write_index(self._index, str(self._index_path))
        self._metadata_path.write_text(json.dumps(self._metadata))

    def add(self, chunks: list[Chunk], embeddings: np.ndarray) -> None:
        if len(chunks) != embeddings.shape[0]:
            raise ValueError("chunks and embeddings must have the same length")
        if not chunks:
            return
        with self._lock:
            ids = np.arange(self._next_id, self._next_id + len(chunks), dtype=np.int64)
            self._index.add_with_ids(embeddings.astype(np.float32), ids)
            for internal_id, chunk in zip(ids.tolist(), chunks):
                self._metadata[internal_id] = asdict(chunk)
            self._next_id += len(chunks)
            self._save()

    def search(self, query_embedding: np.ndarray, top_k: int = 5) -> list[SearchResult]:
        with self._lock:
            if self._index.ntotal == 0:
                return []
            top_k = min(top_k, self._index.ntotal)
            scores, ids = self._index.search(
                query_embedding.astype(np.float32).reshape(1, -1), top_k
            )

        results = []
        for score, internal_id in zip(scores[0].tolist(), ids[0].tolist()):
            if internal_id == -1:
                continue
            meta = self._metadata[internal_id]
            results.append(
                SearchResult(
                    document_id=meta["document_id"],
                    filename=meta["filename"],
                    chunk_id=meta["chunk_id"],
                    chunk_index=meta["chunk_index"],
                    text=meta["text"],
                    score=float(score),
                )
            )
        return results


_instance: FaissVectorStore | None = None
_instance_lock = threading.Lock()


def get_vector_store() -> FaissVectorStore:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                from rag.services.embedding import get_embedding_service

                dimension = get_embedding_service().dimension
                _instance = FaissVectorStore(dimension=dimension)
    return _instance
