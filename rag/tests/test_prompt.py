"""Unit tests for grounded-prompt construction and answer/source validation.

No LLM call here — LLMResponse is constructed by hand to test validate_answer's
grounding logic (the part that doesn't trust the model) in isolation.
"""

from django.test import SimpleTestCase

from rag.services.llm import LLMResponse
from rag.services.prompt import build_user_prompt, validate_answer
from rag.services.vector_store import SearchResult


def make_result(chunk_id, filename="doc.txt", text="chunk text"):
    return SearchResult(
        document_id="doc-1",
        filename=filename,
        chunk_id=chunk_id,
        chunk_index=0,
        text=text,
        score=0.9,
    )


class BuildUserPromptTests(SimpleTestCase):
    def test_no_retrieved_chunks_states_that_explicitly(self):
        prompt = build_user_prompt("What is X?", [])
        self.assertIn("No relevant context was found", prompt)
        self.assertIn("What is X?", prompt)

    def test_retrieved_chunks_are_tagged_with_id_and_document(self):
        chunk = make_result("doc-1:0", filename="handbook.txt", text="Vacation policy is X.")
        prompt = build_user_prompt("What is the vacation policy?", [chunk])

        self.assertIn("chunk_id: doc-1:0", prompt)
        self.assertIn("document: handbook.txt", prompt)
        self.assertIn("Vacation policy is X.", prompt)
        self.assertIn("What is the vacation policy?", prompt)


class ValidateAnswerTests(SimpleTestCase):
    def test_keeps_sources_that_match_retrieved_chunk_ids(self):
        retrieved = [make_result("doc-1:0"), make_result("doc-1:1")]
        response = LLMResponse(
            answer="The answer.",
            sources=[{"document": "doc.txt", "chunk_id": "doc-1:0"}],
            stop_reason="end_turn",
        )

        validated = validate_answer(response, retrieved)

        self.assertEqual(validated.answer, "The answer.")
        self.assertEqual(validated.sources, [{"document": "doc.txt", "chunk_id": "doc-1:0"}])
        self.assertEqual(validated.dropped_unverifiable_sources, 0)

    def test_drops_a_cited_chunk_id_that_was_never_retrieved(self):
        retrieved = [make_result("doc-1:0")]
        response = LLMResponse(
            answer="The answer.",
            sources=[
                {"document": "doc.txt", "chunk_id": "doc-1:0"},
                {"document": "doc.txt", "chunk_id": "doc-1:99"},  # fabricated
            ],
            stop_reason="end_turn",
        )

        validated = validate_answer(response, retrieved)

        self.assertEqual(validated.sources, [{"document": "doc.txt", "chunk_id": "doc-1:0"}])
        self.assertEqual(validated.dropped_unverifiable_sources, 1)

    def test_empty_sources_are_valid_when_the_model_could_not_answer(self):
        response = LLMResponse(answer="I don't know.", sources=[], stop_reason="end_turn")

        validated = validate_answer(response, [make_result("doc-1:0")])

        self.assertEqual(validated.sources, [])
        self.assertEqual(validated.dropped_unverifiable_sources, 0)

    def test_malformed_source_shape_raises_value_error(self):
        response = LLMResponse(
            answer="The answer.",
            sources=[{"document": "doc.txt"}],  # missing chunk_id
            stop_reason="end_turn",
        )

        with self.assertRaises(ValueError):
            validate_answer(response, [make_result("doc-1:0")])
