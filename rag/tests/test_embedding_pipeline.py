"""Integration test for the real embedding model (FastEmbed) feeding a real
FAISS index — this is the one test that actually exercises "does semantic
retrieval work," not just "is the plumbing wired up."

Loads the real ONNX model via get_embedding_service(), so the first run in a
fresh environment needs network access to download model weights (cached
under the HuggingFace cache afterward). This is intentionally separate from
the API-level tests (test_api.py), which mock the embedding/vector-store
boundary to stay fast and fully deterministic.
"""

import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from rag.services.chunking import Chunk, ChunkingService
from rag.services.embedding import get_embedding_service
from rag.services.ingestion import IngestionService
from rag.services.vector_store import FaissVectorStore
from rag.tests.pdf_fixtures import build_minimal_pdf


class EmbeddingPipelineTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.embedding = get_embedding_service()

    def test_document_and_query_embeddings_share_dimension(self):
        chunks = [Chunk("doc-1", "doc.txt", "doc-1:0", 0, "The sky is blue.")]
        doc_vectors = self.embedding.embed_documents(chunks)
        query_vector = self.embedding.embed_query("What color is the sky?")

        self.assertEqual(doc_vectors.shape, (1, self.embedding.dimension))
        self.assertEqual(query_vector.shape, (self.embedding.dimension,))

    def test_empty_chunk_list_embeds_to_an_empty_array(self):
        vectors = self.embedding.embed_documents([])
        self.assertEqual(vectors.shape, (0, self.embedding.dimension))

    def test_semantically_relevant_chunk_is_retrieved_over_unrelated_chunk(self):
        chunks = [
            Chunk("doc-1", "doc.txt", "doc-1:0", 0, "The FAISS index stores vector embeddings for search."),
            Chunk("doc-1", "doc.txt", "doc-1:1", 1, "The office kitchen coffee machine is broken again."),
        ]
        embeddings = self.embedding.embed_documents(chunks)

        store = FaissVectorStore(dimension=self.embedding.dimension, store_dir=Path(self._tmp.name))
        store.add(chunks, embeddings)

        query_vector = self.embedding.embed_query("How does the system search for similar vectors?")
        results = store.search(query_vector, top_k=2)

        self.assertEqual(results[0].chunk_id, "doc-1:0")
        self.assertGreater(results[0].score, results[1].score)

    def test_pdf_extracted_text_is_chunked_embedded_and_retrieved(self):
        """Full path: PDF bytes -> extraction -> cleaning -> chunking ->
        real embeddings -> FAISS -> semantic retrieval.

        Two separate single-page PDFs (rather than two pages of one PDF) so
        each yields exactly one chunk with default settings — chunking is
        page-boundary-agnostic by design (see docs/decisions), so pages of
        the same PDF short enough to fit in one 500-char chunk would merge.
        """
        relevant_pdf = build_minimal_pdf(["The FAISS index stores vector embeddings for search."])
        unrelated_pdf = build_minimal_pdf(["The office kitchen coffee machine is broken again."])

        ingestion = IngestionService()
        chunking = ChunkingService(chunk_size=500, chunk_overlap=0)

        chunks = []
        for pdf_bytes, filename in [(relevant_pdf, "relevant.pdf"), (unrelated_pdf, "unrelated.pdf")]:
            ingested = ingestion.ingest(pdf_bytes, filename)
            chunks += chunking.chunk(ingested.document_id, ingested.filename, ingested.text)

        self.assertEqual(len(chunks), 2)

        embeddings = self.embedding.embed_documents(chunks)

        store = FaissVectorStore(dimension=self.embedding.dimension, store_dir=Path(self._tmp.name))
        store.add(chunks, embeddings)

        query_vector = self.embedding.embed_query("How does the system search for similar vectors?")
        results = store.search(query_vector, top_k=2)

        self.assertEqual(results[0].filename, "relevant.pdf")
        self.assertIn("FAISS index", results[0].text)
        self.assertGreater(results[0].score, results[1].score)
