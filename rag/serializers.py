from rest_framework import serializers

from rag.models import Document


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            "id",
            "filename",
            "uploaded_at",
            "char_count",
            "chunk_count",
            "page_count",
            "status",
            "error_message",
        ]


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class QueryRequestSerializer(serializers.Serializer):
    question = serializers.CharField(allow_blank=False, trim_whitespace=True)


class SourceSerializer(serializers.Serializer):
    document = serializers.CharField()
    chunk_id = serializers.CharField()


class QueryResponseSerializer(serializers.Serializer):
    answer = serializers.CharField()
    sources = SourceSerializer(many=True)
