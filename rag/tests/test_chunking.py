"""Unit tests for ChunkingService — pure function, no Django/storage dependency."""

from django.test import SimpleTestCase

from rag.services.chunking import ChunkingService


class ChunkingServiceTests(SimpleTestCase):
    def test_empty_text_produces_no_chunks(self):
        service = ChunkingService(chunk_size=10, chunk_overlap=2)
        self.assertEqual(service.chunk("doc-1", "a.txt", ""), [])

    def test_short_text_produces_a_single_chunk(self):
        service = ChunkingService(chunk_size=100, chunk_overlap=10)
        chunks = service.chunk("doc-1", "a.txt", "hello world")

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, "hello world")
        self.assertEqual(chunks[0].chunk_index, 0)
        self.assertEqual(chunks[0].chunk_id, "doc-1:0")
        self.assertEqual(chunks[0].document_id, "doc-1")
        self.assertEqual(chunks[0].filename, "a.txt")

    def test_long_text_is_split_into_multiple_chunks(self):
        text = "x" * 25
        service = ChunkingService(chunk_size=10, chunk_overlap=0)
        chunks = service.chunk("doc-1", "a.txt", text)

        # 25 chars / 10-char window, no overlap -> 3 chunks (10, 10, 5)
        self.assertEqual(len(chunks), 3)
        self.assertEqual([c.chunk_index for c in chunks], [0, 1, 2])
        self.assertEqual(sum(len(c.text) for c in chunks), 25)

    def test_overlap_repeats_boundary_text_across_chunks(self):
        text = "abcdefghij"  # 10 chars
        service = ChunkingService(chunk_size=6, chunk_overlap=2)
        chunks = service.chunk("doc-1", "a.txt", text)

        # window 0: 0-6 "abcdef", step = 6-2 = 4
        # window 1: 4-10 "efghij"
        self.assertEqual(chunks[0].text, "abcdef")
        self.assertEqual(chunks[1].text, "efghij")
        # the last 2 chars of chunk 0 equal the first 2 chars of chunk 1
        self.assertEqual(chunks[0].text[-2:], chunks[1].text[:2])

    def test_chunk_ids_are_unique_and_ordered(self):
        service = ChunkingService(chunk_size=5, chunk_overlap=1)
        chunks = service.chunk("doc-1", "a.txt", "x" * 23)

        ids = [c.chunk_id for c in chunks]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, [f"doc-1:{i}" for i in range(len(chunks))])

    def test_rejects_non_positive_chunk_size(self):
        with self.assertRaises(ValueError):
            ChunkingService(chunk_size=0, chunk_overlap=0)

    def test_rejects_negative_overlap(self):
        with self.assertRaises(ValueError):
            ChunkingService(chunk_size=10, chunk_overlap=-1)

    def test_rejects_overlap_not_smaller_than_chunk_size(self):
        with self.assertRaises(ValueError):
            ChunkingService(chunk_size=10, chunk_overlap=10)
