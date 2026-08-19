from django.contrib import admin

from rag.models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["filename", "status", "chunk_count", "char_count", "uploaded_at"]
    list_filter = ["status"]
    readonly_fields = ["id", "uploaded_at"]
