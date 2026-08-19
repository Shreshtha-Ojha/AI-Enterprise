"""RAG prompt template and structured-output validation.

Two responsibilities live here: building the grounded prompt sent to the
LLM, and validating that what comes back actually matches the shape callers
depend on. The LLM service (rag/services/llm.py) already asks the model for
JSON matching a schema (output_config.format) — this module is the second,
independent check: schema-shaped is not the same as trustworthy, so we also
verify every cited chunk_id was actually part of the retrieved context.
"""

from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from rag.services.llm import LLMResponse
from rag.services.vector_store import SearchResult

SYSTEM_PROMPT = """You are a knowledge assistant for an internal enterprise knowledge base.

Answer the user's question using ONLY the information in the "Context" \
section of the user message. Follow these rules strictly:

1. Never use outside knowledge, training data, or assumptions beyond what \
the context contains, even if you are confident it is correct.
2. If the context does not contain enough information to answer the \
question, say so explicitly and plainly in the "answer" field — do not \
guess, and do not partially answer with unsupported details.
3. Every claim in "answer" must be traceable to the supplied context.
4. List every context chunk you actually drew from in "sources", citing \
its chunk_id exactly as given. If you could not answer from the context, \
"sources" must be an empty list.
5. Do not fabricate a chunk_id. Only cite chunk_ids that appear in the \
Context section below.
"""


def build_user_prompt(question: str, retrieved_chunks: list[SearchResult]) -> str:
    if not retrieved_chunks:
        context_block = "(No relevant context was found in the knowledge base.)"
    else:
        context_block = "\n\n".join(
            f"[chunk_id: {chunk.chunk_id} | document: {chunk.filename}]\n{chunk.text}"
            for chunk in retrieved_chunks
        )
    return (
        f"Context:\n{context_block}\n\n"
        f"Question: {question}\n\n"
        "Respond with an answer grounded strictly in the context above."
    )


class SourceModel(BaseModel):
    document: str
    chunk_id: str


class AnswerModel(BaseModel):
    answer: str
    sources: list[SourceModel]


@dataclass(frozen=True)
class ValidatedAnswer:
    answer: str
    sources: list[dict]
    dropped_unverifiable_sources: int


def validate_answer(llm_response: LLMResponse, retrieved_chunks: list[SearchResult]) -> ValidatedAnswer:
    """Validate structure, then validate grounding.

    Structural validation catches a model that didn't comply with the
    requested schema (defense in depth on top of output_config.format).
    Grounding validation catches a model that returned well-formed JSON but
    cited a chunk_id it made up rather than one that was actually retrieved
    — dropping those sources rather than trusting them blindly.
    """
    try:
        parsed = AnswerModel(answer=llm_response.answer, sources=llm_response.sources)
    except ValidationError as exc:
        raise ValueError(f"Model response did not match the expected structure: {exc}") from exc

    retrieved_chunk_ids = {chunk.chunk_id for chunk in retrieved_chunks}
    verified_sources = [
        source.model_dump() for source in parsed.sources if source.chunk_id in retrieved_chunk_ids
    ]
    dropped = len(parsed.sources) - len(verified_sources)

    return ValidatedAnswer(
        answer=parsed.answer,
        sources=verified_sources,
        dropped_unverifiable_sources=dropped,
    )
