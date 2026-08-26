"""URL configuration for the Knowledge Retrieval Gateway."""

from django.urls import path

from .views import KnowledgeSearchView

app_name = "knowledge"

urlpatterns = [
    path("knowledge/search/", KnowledgeSearchView.as_view(), name="knowledge_search"),
]
