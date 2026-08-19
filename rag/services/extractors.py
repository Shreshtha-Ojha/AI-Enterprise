"""Text extraction abstraction — one extractor per supported source format.

Adding a new format (e.g. PDF) means writing a new TextExtractor subclass and
registering it in EXTRACTORS. Nothing else in the pipeline needs to change.
"""

from abc import ABC, abstractmethod


class UnsupportedFileTypeError(Exception):
    pass


class TextExtractor(ABC):
    @abstractmethod
    def extract(self, file_bytes: bytes) -> str:
        """Return raw text extracted from the given file's bytes."""


class TxtExtractor(TextExtractor):
    def extract(self, file_bytes: bytes) -> str:
        return file_bytes.decode("utf-8", errors="replace")


EXTRACTORS: dict[str, TextExtractor] = {
    ".txt": TxtExtractor(),
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
