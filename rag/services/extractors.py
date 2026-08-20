"""Text extraction abstraction — one extractor per supported source format.

Adding a new format means writing a new TextExtractor subclass and
registering it in EXTRACTORS. Nothing else in the pipeline needs to change —
this is exactly how PDF support was added (see PdfExtractor below).
"""

import io
from abc import ABC, abstractmethod

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class UnsupportedFileTypeError(Exception):
    pass


class ExtractionError(Exception):
    """Raised when a file has a supported extension but its content can't be
    parsed (e.g. a corrupted or non-PDF file renamed to .pdf)."""


class TextExtractor(ABC):
    @abstractmethod
    def extract(self, file_bytes: bytes) -> str:
        """Return raw text extracted from the given file's bytes."""

    def extract_metadata(self, file_bytes: bytes) -> dict:
        """Return extractor-specific metadata (e.g. page count).

        Empty by default — most formats have nothing worth surfacing.
        """
        return {}


class TxtExtractor(TextExtractor):
    def extract(self, file_bytes: bytes) -> str:
        return file_bytes.decode("utf-8", errors="replace")


class PdfExtractor(TextExtractor):
    """Extracts text from text-based PDFs via pypdf.

    Scanned/image-only PDFs have no embedded text layer, so extraction
    yields an empty (or near-empty) string for them — the same "no
    extractable text" path that whitespace-only .txt files already hit in
    the ingestion pipeline. There is no OCR fallback.
    """

    def extract(self, file_bytes: bytes) -> str:
        reader = self._read(file_bytes)
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)

    def extract_metadata(self, file_bytes: bytes) -> dict:
        reader = self._read(file_bytes)
        return {"page_count": len(reader.pages)}

    @staticmethod
    def _read(file_bytes: bytes) -> PdfReader:
        if not file_bytes:
            raise ExtractionError("The uploaded PDF is empty.")
        try:
            return PdfReader(io.BytesIO(file_bytes))
        except (PdfReadError, ValueError) as exc:
            raise ExtractionError(f"Could not read PDF: {exc}") from exc


EXTRACTORS: dict[str, TextExtractor] = {
    ".txt": TxtExtractor(),
    ".pdf": PdfExtractor(),
}


def get_extractor(filename: str) -> TextExtractor:
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    extractor = EXTRACTORS.get(suffix)
    if extractor is None:
        supported = ", ".join(sorted(EXTRACTORS))
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{suffix or filename}'. Supported: {supported}"
        )
    return extractor
