from django.urls import path

from rag.views import DocumentListView, DocumentUploadView, QueryView

urlpatterns = [
    path("documents/upload", DocumentUploadView.as_view(), name="document-upload"),
    path("documents", DocumentListView.as_view(), name="document-list"),
    path("query", QueryView.as_view(), name="query"),
]
