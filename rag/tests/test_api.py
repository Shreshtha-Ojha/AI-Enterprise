"""API-level tests for the three REST endpoints.

These use the real ingestion pipeline (real FastEmbed embeddings, real FAISS
index against an isolated temp directory) so that response shapes and
document bookkeeping are verified against actual behavior, not a mock. Only
the LLM provider boundary is mocked — this is deliberately NOT an Anthropic
integration test (no real model call, no assertion about answer quality);
it verifies that the query view/pipeline wiring maps each outcome (success,
LLMOutputError, missing-API-key RuntimeError) to the right HTTP response.
There is currently no live-Anthropic test in this suite — see README/
CHANGELOG for why (no usable API credits in this environment).
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

import rag.services.vector_store as vector_store_module
from rag.models import Document
from rag.services.llm import LLMOutputError, LLMResponse
from rag.tests.pdf_fixtures import build_blank_pdf, build_minimal_pdf


class RagApiTestCase(TestCase):
    """Points the vector store at an isolated temp dir and resets the
    process-wide singleton so tests don't read/write the real dev index."""

    def setUp(self):
        self.client = APIClient()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

        self._settings_override = override_settings(RAG_VECTOR_STORE_DIR=Path(self._tmp.name))
        self._settings_override.enable()
        self.addCleanup(self._settings_override.disable)

        vector_store_module._instance = None
        self.addCleanup(self._reset_vector_store_singleton)

    def _reset_vector_store_singleton(self):
        vector_store_module._instance = None

    def upload_txt(self, content: str, filename: str = "notes.txt"):
        upload = SimpleUploadedFile(filename, content.encode("utf-8"), content_type="text/plain")
        return self.client.post("/api/documents/upload", {"file": upload}, format="multipart")

    def upload_pdf(self, pdf_bytes: bytes, filename: str = "notes.pdf"):
        upload = SimpleUploadedFile(filename, pdf_bytes, content_type="application/pdf")
        return self.client.post("/api/documents/upload", {"file": upload}, format="multipart")


class DocumentUploadViewTests(RagApiTestCase):
    def test_upload_supported_file_returns_201_with_document_shape(self):
        response = self.upload_txt("The vector store uses FAISS for similarity search.")

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["filename"], "notes.txt")
        self.assertEqual(body["status"], "ready")
        self.assertGreater(body["chunk_count"], 0)
        self.assertGreater(body["char_count"], 0)
        self.assertEqual(body["error_message"], "")
        self.assertIn("id", body)
        self.assertIn("uploaded_at", body)

    def test_upload_persists_a_document_row(self):
        self.upload_txt("Some content.")
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(Document.objects.first().status, Document.Status.READY)

    def test_upload_unsupported_extension_returns_400(self):
        upload = SimpleUploadedFile("report.docx", b"binary content", content_type="application/octet-stream")
        response = self.client.post("/api/documents/upload", {"file": upload}, format="multipart")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file type", response.json()["detail"])

    def test_upload_missing_file_returns_400_validation_error(self):
        response = self.client.post("/api/documents/upload", {}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("file", response.json())

    def test_upload_whitespace_only_file_is_recorded_as_failed_not_500(self):
        response = self.upload_txt("   \n\n   ")

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "failed")
        self.assertEqual(body["chunk_count"], 0)
        self.assertTrue(body["error_message"])

    def test_upload_valid_pdf_returns_201_with_page_count(self):
        pdf_bytes = build_minimal_pdf(["The vector store uses FAISS for similarity search."])
        response = self.upload_pdf(pdf_bytes)

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["filename"], "notes.pdf")
        self.assertEqual(body["status"], "ready")
        self.assertGreater(body["chunk_count"], 0)
        self.assertEqual(body["page_count"], 1)

    def test_upload_multi_page_pdf_reports_correct_page_count(self):
        pdf_bytes = build_minimal_pdf(["Page one.", "Page two.", "Page three."])
        response = self.upload_pdf(pdf_bytes)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["page_count"], 3)

    def test_upload_txt_has_null_page_count(self):
        response = self.upload_txt("Some content.")
        self.assertIsNone(response.json()["page_count"])

    def test_upload_corrupt_pdf_returns_400(self):
        response = self.upload_pdf(b"this is not a valid pdf")

        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())

    def test_upload_empty_pdf_returns_400(self):
        # DRF's FileField rejects zero-byte uploads at the serializer level
        # (before extraction runs), so the error shape is {"file": [...]}
        # rather than the {"detail": ...} shape ExtractionError produces.
        response = self.upload_pdf(b"")

        self.assertEqual(response.status_code, 400)
        self.assertIn("file", response.json())

    def test_upload_scanned_pdf_with_no_text_is_recorded_as_failed_not_500(self):
        pdf_bytes = build_blank_pdf(1)
        response = self.upload_pdf(pdf_bytes)

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "failed")
        self.assertEqual(body["chunk_count"], 0)
        self.assertTrue(body["error_message"])


class DocumentListViewTests(RagApiTestCase):
    def test_list_empty_returns_empty_list(self):
        response = self.client.get("/api/documents")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_list_returns_uploaded_documents_newest_first(self):
        self.upload_txt("first document content.", filename="first.txt")
        self.upload_txt("second document content.", filename="second.txt")

        response = self.client.get("/api/documents")

        self.assertEqual(response.status_code, 200)
        filenames = [doc["filename"] for doc in response.json()]
        self.assertEqual(filenames, ["second.txt", "first.txt"])


class QueryViewTests(RagApiTestCase):
    def test_blank_question_returns_400(self):
        response = self.client.post("/api/query", {"question": ""}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("question", response.json())

    def test_missing_question_field_returns_400(self):
        response = self.client.post("/api/query", {}, format="json")
        self.assertEqual(response.status_code, 400)

    @patch("rag.services.pipeline.get_llm_provider")
    def test_successful_query_returns_grounded_answer_and_sources(self, mock_get_llm):
        upload_response = self.upload_txt("FAISS is used for the vector index in this project.")
        chunk_id = f"{upload_response.json()['id']}:0"

        mock_provider = mock_get_llm.return_value
        mock_provider.generate_structured_answer.return_value = LLMResponse(
            answer="FAISS is used for the vector index.",
            sources=[{"document": "notes.txt", "chunk_id": chunk_id}],
            stop_reason="end_turn",
        )

        response = self.client.post("/api/query", {"question": "What is used for the vector index?"}, format="json")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["answer"], "FAISS is used for the vector index.")
        self.assertEqual(body["sources"], [{"document": "notes.txt", "chunk_id": chunk_id}])

    @patch("rag.services.pipeline.get_llm_provider")
    def test_successful_query_returns_grounded_answer_and_sources_from_pdf_document(self, mock_get_llm):
        pdf_bytes = build_minimal_pdf(["FAISS is used for the vector index in this project."])
        upload_response = self.upload_pdf(pdf_bytes, filename="notes.pdf")
        chunk_id = f"{upload_response.json()['id']}:0"

        mock_provider = mock_get_llm.return_value
        mock_provider.generate_structured_answer.return_value = LLMResponse(
            answer="FAISS is used for the vector index.",
            sources=[{"document": "notes.pdf", "chunk_id": chunk_id}],
            stop_reason="end_turn",
        )

        response = self.client.post("/api/query", {"question": "What is used for the vector index?"}, format="json")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["answer"], "FAISS is used for the vector index.")
        self.assertEqual(body["sources"], [{"document": "notes.pdf", "chunk_id": chunk_id}])

    @patch("rag.services.pipeline.get_llm_provider")
    def test_fabricated_source_chunk_id_is_dropped(self, mock_get_llm):
        self.upload_txt("FAISS is used for the vector index in this project.")

        mock_provider = mock_get_llm.return_value
        mock_provider.generate_structured_answer.return_value = LLMResponse(
            answer="An answer.",
            sources=[{"document": "notes.txt", "chunk_id": "not-a-real-chunk-id"}],
            stop_reason="end_turn",
        )

        response = self.client.post("/api/query", {"question": "What is used?"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sources"], [])

    @patch("rag.services.pipeline.get_llm_provider")
    def test_llm_output_error_returns_502(self, mock_get_llm):
        mock_provider = mock_get_llm.return_value
        mock_provider.generate_structured_answer.side_effect = LLMOutputError("The model declined to answer.")

        response = self.client.post("/api/query", {"question": "Anything?"}, format="json")

        self.assertEqual(response.status_code, 502)
        self.assertIn("detail", response.json())

    @patch("rag.services.pipeline.get_llm_provider")
    def test_missing_api_key_returns_503_not_a_stack_trace(self, mock_get_llm):
        mock_get_llm.side_effect = RuntimeError("ANTHROPIC_API_KEY is not set.")

        response = self.client.post("/api/query", {"question": "Anything?"}, format="json")

        self.assertEqual(response.status_code, 503)
        self.assertIn("detail", response.json())

    def test_query_with_no_documents_uploaded_still_returns_a_clean_response_shape(self):
        with patch("rag.services.pipeline.get_llm_provider") as mock_get_llm:
            mock_provider = mock_get_llm.return_value
            mock_provider.generate_structured_answer.return_value = LLMResponse(
                answer="I don't know — no relevant information was found.",
                sources=[],
                stop_reason="end_turn",
            )
            response = self.client.post("/api/query", {"question": "Anything?"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sources"], [])
