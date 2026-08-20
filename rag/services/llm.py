"""LLM service — isolated provider implementation.

LLMProvider is the seam: callers depend only on this interface, not on the
Anthropic SDK. Swapping providers later means writing a new LLMProvider
subclass, not touching the pipeline or the views.
"""

import json
import logging
import os
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass

import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)

ANSWER_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "document": {"type": "string"},
                    "chunk_id": {"type": "string"},
                },
                "required": ["document", "chunk_id"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answer", "sources"],
    "additionalProperties": False,
}


class LLMOutputError(Exception):
    """Raised when the model's response can't be trusted as-is (parse failure
    or refusal) — callers decide how to surface this to the user."""


@dataclass(frozen=True)
class LLMResponse:
    answer: str
    sources: list[dict]
    stop_reason: str


class LLMProvider(ABC):
    @abstractmethod
    def generate_structured_answer(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Send a grounded prompt and return a parsed, schema-shaped answer."""


class AnthropicLLMProvider(LLMProvider):
    def __init__(self, model: str | None = None):
        # anthropic.Anthropic() reads ANTHROPIC_API_KEY from the environment
        # on its own — the key is never read or stored here directly, and
        # never hardcoded.
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        self._client = anthropic.Anthropic()
        self._model = model or settings.RAG_LLM_MODEL

    def generate_structured_answer(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                output_config={
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": ANSWER_JSON_SCHEMA},
                },
            )
        except anthropic.APIError as exc:
            # Covers everything the SDK can raise for a failed call: auth
            # failures, exhausted credits, rate limits, timeouts, connection
            # errors. The full detail is logged server-side for debugging;
            # callers only see a generic, safe message — never the raw SDK
            # exception (which can include request/account-specific detail).
            logger.error("Anthropic API request failed: %s", exc, exc_info=True)
            raise LLMOutputError(
                "The LLM provider is currently unavailable. Please try again later."
            ) from exc

        if response.stop_reason == "refusal":
            raise LLMOutputError("The model declined to answer this question.")

        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            raise LLMOutputError("The model returned no text content.")

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMOutputError(f"Model output was not valid JSON: {exc}") from exc

        return LLMResponse(
            answer=data.get("answer", ""),
            sources=data.get("sources", []),
            stop_reason=response.stop_reason,
        )


_instance: LLMProvider | None = None
_lock = threading.Lock()


def get_llm_provider() -> LLMProvider:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = AnthropicLLMProvider()
    return _instance
