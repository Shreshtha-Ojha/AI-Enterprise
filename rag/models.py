import uuid

from django.db import models


class Document(models.Model):
    """Bookkeeping record for an uploaded document.

    Deliberately minimal and unscoped (no owner/organization FK) per the
    current phase's scope. Chunk text and embeddings do NOT live here — they
    live in the FAISS-backed vector store (see rag/services/vector_store.py)
    so this model stays a thin listing/status record, not a second copy of
    document content.
    """

    class Status(models.TextChoices):
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    char_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.READY)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return f"{self.filename} ({self.id})"
