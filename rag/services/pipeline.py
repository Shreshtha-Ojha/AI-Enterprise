"""Pipeline orchestration — the only place that wires the services together.

Views call these two functions and nothing else from the services package
directly (beyond the exceptions they need to catch). Keeping orchestration
here, instead of in views.py, is what keeps views thin.
"""

from dataclasses import dataclass

from django.conf import settings

from rag.models import Document
from rag.services.chunking import ChunkingService
from rag.services.embedding import get_embedding_service
from rag.services.ingestion import IngestionService
from rag.services.llm import get_llm_provider
from rag.services.prompt import SYSTEM_PROMPT, build_user_prompt, validate_answer
from rag.services.vector_store import get_vector_store


def run_ingestion_pipeline(file_bytes: bytes, filename: str) -> Document:
    """Document -> text extraction -> cleaning -> chunking -> embedding -> vector index."""
    ingestion = IngestionService()
    chunking = ChunkingService(
        chunk_size=settings.RAG_CHUNK_SIZE, chunk_overlap=settings.RAG_CHUNK_OVERLAP
    )
    embedding = get_embedding_service()
    vector_store = get_vector_store()

    ingested = ingestion.ingest(file_bytes, filename)
    chunks = chunking.chunk(ingested.document_id, ingested.filename, ingested.text)

    if not chunks:
        return Document.objects.create(
            id=ingested.document_id,
            filename=ingested.filename,
            char_count=ingested.char_count,
            chunk_count=0,
            status=Document.Status.FAILED,
            error_message="Document contained no extractable text after cleaning.",
        )

    embeddings = embedding.embed_documents(chunks)
    vector_store.add(chunks, embeddings)

    return Document.objects.create(
        id=ingested.document_id,
        filename=ingested.filename,
        char_count=ingested.char_count,
        chunk_count=len(chunks),
        status=Document.Status.READY,
    )


@dataclass(frozen=True)
class QueryResult:
    answer: str
    sources: list[dict]


def run_query_pipeline(question: str) -> QueryResult:
    """User question -> question embedding -> similarity retrieval ->
    grounded prompt -> LLM -> structured answer + sources."""
    embedding = get_embedding_service()
    vector_store = get_vector_store()
    llm = get_llm_provider()

    query_vector = embedding.embed_query(question)
    retrieved = vector_store.search(query_vector, top_k=settings.RAG_TOP_K)

    user_prompt = build_user_prompt(question, retrieved)
    llm_response = llm.generate_structured_answer(SYSTEM_PROMPT, user_prompt)
    validated = validate_answer(llm_response, retrieved)

    return QueryResult(answer=validated.answer, sources=validated.sources)
