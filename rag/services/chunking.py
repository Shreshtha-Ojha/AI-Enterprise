"""Fixed-size chunking with overlap.

Pure function of (document_id, filename, text) -> list[Chunk]. No Django or
storage dependency, so it's independently testable and swappable — see
docs/learning/chunking.md for why fixed-size was chosen for the MVP and how
semantic chunking would replace it later.
"""

from dataclasses import dataclass

DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50


@dataclass(frozen=True)
class Chunk:
    document_id: str
    filename: str
    chunk_id: str
    chunk_index: int
    text: str


class ChunkingService:
    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE, chunk_overlap: int = DEFAULT_CHUNK_OVERLAP):
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must not be negative")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, document_id: str, filename: str, text: str) -> list[Chunk]:
        if not text:
            return []

        step = self.chunk_size - self.chunk_overlap
        chunks: list[Chunk] = []
        start = 0
        index = 0
        text_length = len(text)

        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    Chunk(
                        document_id=document_id,
                        filename=filename,
                        chunk_id=f"{document_id}:{index}",
                        chunk_index=index,
                        text=chunk_text,
                    )
                )
                index += 1
            if end == text_length:
                break
            start += step

        return chunks
