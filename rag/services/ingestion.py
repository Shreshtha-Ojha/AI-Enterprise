"""Document ingestion service.

Responsible for exactly three things: extracting raw text (via the
extractors module), cleaning obvious whitespace/noise, and assigning a
document identity. It knows nothing about chunking, embeddings, or storage —
those are separate services the pipeline composes.
"""

import re
import uuid
from dataclasses import dataclass

from rag.services.extractors import get_extractor


@dataclass(frozen=True)
class IngestedDocument:
    document_id: str
    filename: str
    text: str
    char_count: int


def clean_text(text: str) -> str:
    """Collapse repeated whitespace/newlines and strip stray control characters.

    Deliberately conservative: this is noise cleanup, not normalization. It
    must not rewrite meaningful content (e.g. don't lowercase, don't strip
    punctuation) since downstream chunks are shown to the user as sources.
    """
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return text.strip()


class IngestionService:
    def ingest(self, file_bytes: bytes, filename: str) -> IngestedDocument:
        extractor = get_extractor(filename)
        raw_text = extractor.extract(file_bytes)
        cleaned = clean_text(raw_text)
        return IngestedDocument(
            document_id=str(uuid.uuid4()),
            filename=filename,
            text=cleaned,
            char_count=len(cleaned),
        )
