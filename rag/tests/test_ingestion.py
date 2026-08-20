"""Unit tests for text extraction and the ingestion/cleaning step."""

from django.test import SimpleTestCase

from rag.services.extractors import ExtractionError, UnsupportedFileTypeError, get_extractor
from rag.services.ingestion import IngestionService, clean_text
from rag.tests.pdf_fixtures import build_blank_pdf, build_minimal_pdf


class ExtractorTests(SimpleTestCase):
    def test_txt_extractor_decodes_utf8(self):
        extractor = get_extractor("notes.txt")
        self.assertEqual(extractor.extract("hello".encode("utf-8")), "hello")

    def test_txt_extractor_has_no_metadata(self):
        extractor = get_extractor("notes.txt")
        self.assertEqual(extractor.extract_metadata(b"hello"), {})

    def test_unsupported_extension_raises(self):
        with self.assertRaises(UnsupportedFileTypeError):
            get_extractor("report.docx")

    def test_filename_with_no_extension_raises(self):
        with self.assertRaises(UnsupportedFileTypeError):
            get_extractor("README")

    def test_extension_matching_is_case_insensitive(self):
        self.assertIsInstance(get_extractor("REPORT.TXT"), type(get_extractor("report.txt")))
        self.assertIsInstance(get_extractor("Report.Pdf"), type(get_extractor("report.pdf")))


class PdfExtractorTests(SimpleTestCase):
    def test_extracts_text_from_a_valid_pdf(self):
        extractor = get_extractor("report.pdf")
        pdf_bytes = build_minimal_pdf(["Hello from a PDF document."])

        text = extractor.extract(pdf_bytes)

        self.assertIn("Hello from a PDF document.", text)

    def test_extracts_text_from_each_page_in_order(self):
        extractor = get_extractor("report.pdf")
        pdf_bytes = build_minimal_pdf(["Page one content.", "Page two content."])

        text = extractor.extract(pdf_bytes)

        self.assertLess(text.index("Page one content."), text.index("Page two content."))

    def test_metadata_reports_page_count(self):
        extractor = get_extractor("report.pdf")
        pdf_bytes = build_minimal_pdf(["one", "two", "three"])

        self.assertEqual(extractor.extract_metadata(pdf_bytes), {"page_count": 3})

    def test_blank_pdf_extracts_to_empty_text(self):
        extractor = get_extractor("report.pdf")
        pdf_bytes = build_blank_pdf(1)

        self.assertEqual(extractor.extract(pdf_bytes).strip(), "")

    def test_empty_bytes_raise_extraction_error(self):
        extractor = get_extractor("report.pdf")
        with self.assertRaises(ExtractionError):
            extractor.extract(b"")

    def test_non_pdf_bytes_raise_extraction_error(self):
        extractor = get_extractor("report.pdf")
        with self.assertRaises(ExtractionError):
            extractor.extract(b"this is not a pdf file")


class CleanTextTests(SimpleTestCase):
    def test_collapses_repeated_spaces_and_tabs(self):
        self.assertEqual(clean_text("a    b\t\tc"), "a b c")

    def test_collapses_three_or_more_blank_lines_to_two(self):
        self.assertEqual(clean_text("a\n\n\n\n\nb"), "a\n\nb")

    def test_strips_null_bytes(self):
        self.assertEqual(clean_text("a\x00b"), "ab")

    def test_strips_leading_and_trailing_whitespace(self):
        self.assertEqual(clean_text("   hello   "), "hello")

    def test_does_not_alter_meaningful_casing_or_punctuation(self):
        self.assertEqual(clean_text("Hello, World!"), "Hello, World!")


class IngestionServiceTests(SimpleTestCase):
    def test_ingest_returns_cleaned_text_and_char_count(self):
        service = IngestionService()
        result = service.ingest(b"  Hello   World  ", "notes.txt")

        self.assertEqual(result.text, "Hello World")
        self.assertEqual(result.char_count, len("Hello World"))
        self.assertEqual(result.filename, "notes.txt")
        self.assertTrue(result.document_id)

    def test_ingest_assigns_a_unique_document_id_per_call(self):
        service = IngestionService()
        first = service.ingest(b"one", "a.txt")
        second = service.ingest(b"two", "a.txt")

        self.assertNotEqual(first.document_id, second.document_id)

    def test_ingest_raises_for_unsupported_format(self):
        service = IngestionService()
        with self.assertRaises(UnsupportedFileTypeError):
            service.ingest(b"binary", "file.docx")

    def test_ingest_pdf_returns_cleaned_text_and_page_count_metadata(self):
        service = IngestionService()
        pdf_bytes = build_minimal_pdf(["Hello   World"])

        result = service.ingest(pdf_bytes, "notes.pdf")

        self.assertEqual(result.text, "Hello World")
        self.assertEqual(result.filename, "notes.pdf")
        self.assertEqual(result.metadata, {"page_count": 1})

    def test_ingest_txt_has_empty_metadata(self):
        service = IngestionService()
        result = service.ingest(b"hello", "notes.txt")

        self.assertEqual(result.metadata, {})

    def test_ingest_raises_extraction_error_for_corrupt_pdf(self):
        service = IngestionService()
        with self.assertRaises(ExtractionError):
            service.ingest(b"not a real pdf", "notes.pdf")
