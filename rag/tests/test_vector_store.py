"""Integration tests for FaissVectorStore: real FAISS index, real disk I/O,
synthetic (hand-built) vectors instead of FastEmbed — this isolates "does
FAISS storage/retrieval stay aligned with chunk metadata" from "does the
embedding model produce good vectors" (covered separately, see
test_embedding_pipeline.py).
"""

import tempfile
from pathlib import Path

import numpy as np
from django.test import SimpleTestCase

from rag.services.chunking import Chunk
from rag.services.vector_store import FaissVectorStore

DIMENSION = 4


def make_chunk(chunk_id, text="text"):
    return Chunk(document_id="doc-1", filename="doc.txt", chunk_id=chunk_id, chunk_index=0, text=text)


def unit_vector(*values):
    vec = np.array(values, dtype=np.float32)
    return vec / np.linalg.norm(vec)


class FaissVectorStoreTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store_dir = Path(self._tmp.name)

    def test_search_on_empty_store_returns_no_results(self):
        store = FaissVectorStore(dimension=DIMENSION, store_dir=self.store_dir)
        results = store.search(unit_vector(1, 0, 0, 0), top_k=5)
        self.assertEqual(results, [])

    def test_search_returns_the_closest_chunk_with_matching_metadata(self):
        store = FaissVectorStore(dimension=DIMENSION, store_dir=self.store_dir)
        chunks = [make_chunk("doc-1:0", "about cats"), make_chunk("doc-1:1", "about cars")]
        embeddings = np.stack([unit_vector(1, 0, 0, 0), unit_vector(0, 1, 0, 0)])

        store.add(chunks, embeddings)
        results = store.search(unit_vector(1, 0, 0, 0), top_k=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk_id, "doc-1:0")
        self.assertEqual(results[0].text, "about cats")
        self.assertEqual(results[0].document_id, "doc-1")
        self.assertAlmostEqual(results[0].score, 1.0, places=5)

    def test_results_are_ordered_by_descending_similarity(self):
        store = FaissVectorStore(dimension=DIMENSION, store_dir=self.store_dir)
        chunks = [make_chunk("doc-1:0"), make_chunk("doc-1:1"), make_chunk("doc-1:2")]
        embeddings = np.stack(
            [unit_vector(1, 0, 0, 0), unit_vector(0.7, 0.7, 0, 0), unit_vector(0, 1, 0, 0)]
        )

        store.add(chunks, embeddings)
        results = store.search(unit_vector(1, 0, 0, 0), top_k=3)

        self.assertEqual([r.chunk_id for r in results], ["doc-1:0", "doc-1:1", "doc-1:2"])
        self.assertTrue(results[0].score >= results[1].score >= results[2].score)

    def test_top_k_larger_than_index_size_does_not_error(self):
        store = FaissVectorStore(dimension=DIMENSION, store_dir=self.store_dir)
        store.add([make_chunk("doc-1:0")], np.stack([unit_vector(1, 0, 0, 0)]))

        results = store.search(unit_vector(1, 0, 0, 0), top_k=50)
        self.assertEqual(len(results), 1)

    def test_mismatched_chunks_and_embeddings_length_raises(self):
        store = FaissVectorStore(dimension=DIMENSION, store_dir=self.store_dir)
        with self.assertRaises(ValueError):
            store.add([make_chunk("doc-1:0")], np.stack([unit_vector(1, 0, 0, 0), unit_vector(0, 1, 0, 0)]))

    def test_index_and_metadata_persist_across_instances(self):
        store = FaissVectorStore(dimension=DIMENSION, store_dir=self.store_dir)
        store.add([make_chunk("doc-1:0", "persisted text")], np.stack([unit_vector(1, 0, 0, 0)]))

        reloaded = FaissVectorStore(dimension=DIMENSION, store_dir=self.store_dir)
        results = reloaded.search(unit_vector(1, 0, 0, 0), top_k=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].text, "persisted text")

    def test_ids_keep_incrementing_across_multiple_add_calls(self):
        store = FaissVectorStore(dimension=DIMENSION, store_dir=self.store_dir)
        store.add([make_chunk("doc-1:0")], np.stack([unit_vector(1, 0, 0, 0)]))
        store.add([make_chunk("doc-1:1")], np.stack([unit_vector(0, 1, 0, 0)]))

        results = store.search(unit_vector(0, 1, 0, 0), top_k=1)
        self.assertEqual(results[0].chunk_id, "doc-1:1")
