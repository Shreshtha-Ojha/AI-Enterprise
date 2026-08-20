"""Unit tests for text extraction and the ingestion/cleaning step."""

from django.test import SimpleTestCase

from rag.services.extractors import UnsupportedFileTypeError, get_extractor
from rag.services.ingestion import IngestionService, clean_text


class ExtractorTests(SimpleTestCase):
    def test_txt_extractor_decodes_utf8(self):
        extractor = get_extractor("notes.txt")
        self.assertEqual(extractor.extract("hello".encode("utf-8")), "hello")

    def test_unsupported_extension_raises(self):
        with self.assertRaises(UnsupportedFileTypeError):
            get_extractor("report.pdf")

    def test_filename_with_no_extension_raises(self):
        with self.assertRaises(UnsupportedFileTypeError):
            get_extractor("README")


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
            service.ingest(b"binary", "file.pdf")
