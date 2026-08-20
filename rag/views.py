from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from rag.models import Document
from rag.serializers import (
    DocumentSerializer,
    DocumentUploadSerializer,
    QueryRequestSerializer,
    QueryResponseSerializer,
)
from rag.services.extractors import ExtractionError, UnsupportedFileTypeError
from rag.services.llm import LLMOutputError
from rag.services.pipeline import run_ingestion_pipeline, run_query_pipeline


class DocumentUploadView(APIView):
    """POST /api/documents/upload — runs the full ingest -> chunk -> embed -> index pipeline."""

    def post(self, request):
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded_file = serializer.validated_data["file"]

        try:
            document = run_ingestion_pipeline(uploaded_file.read(), uploaded_file.name)
        except UnsupportedFileTypeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ExtractionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)


class DocumentListView(ListAPIView):
    """GET /api/documents — lists uploaded documents."""

    queryset = Document.objects.all()
    serializer_class = DocumentSerializer


class QueryView(APIView):
    """POST /api/query — {"question": "..."} -> {"answer": "...", "sources": [...]}."""

    def post(self, request):
        serializer = QueryRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = serializer.validated_data["question"]

        try:
            result = run_query_pipeline(question)
        except LLMOutputError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except RuntimeError as exc:
            # e.g. ANTHROPIC_API_KEY not configured
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        response = QueryResponseSerializer({"answer": result.answer, "sources": result.sources})
        return Response(response.data, status=status.HTTP_200_OK)
