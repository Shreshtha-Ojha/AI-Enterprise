"""Embedding service — the single place embeddings happen.

Every other service works with plain text or chunk metadata; only this
module ever imports FastEmbed or knows an embedding is a 384-dim unit
vector. Swapping the embedding model (or provider) means editing this file
alone.
"""

import threading

import numpy as np
from django.conf import settings
from fastembed import TextEmbedding

from rag.services.chunking import Chunk


class EmbeddingService:
    def __init__(self, model_name: str | None = None):
        self._model_name = model_name or settings.RAG_EMBEDDING_MODEL
        self._model = TextEmbedding(model_name=self._model_name)

    def embed_documents(self, chunks: list[Chunk]) -> np.ndarray:
        """Embed chunk text for storage in the vector index.

        Uses FastEmbed's passage-oriented embedding call, which is the
        correct asymmetric-retrieval counterpart to embed_query below —
        BGE-family models embed queries and passages slightly differently
        so that a query vector and the passage vectors it should match land
        close together in the same space.
        """
        if not chunks:
            return np.empty((0, self.dimension), dtype=np.float32)
        vectors = list(self._model.passage_embed([c.text for c in chunks]))
        return np.array(vectors, dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        vectors = list(self._model.query_embed([query]))
        return np.array(vectors[0], dtype=np.float32)

    @property
    def dimension(self) -> int:
        return self._model.embedding_size


_instance: EmbeddingService | None = None
_lock = threading.Lock()


def get_embedding_service() -> EmbeddingService:
    """Process-wide singleton — FastEmbed loads an ONNX model from disk on
    construction, which is too expensive to redo per request."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = EmbeddingService()
    return _instance
