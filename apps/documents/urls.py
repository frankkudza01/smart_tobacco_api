from django.urls import path

from apps.documents.views import (
    DocumentDetailView,
    DocumentGlobalVerifyView,
    DocumentListCreateView,
    DocumentSuspectListView,
    DocumentVerifyView,
)

urlpatterns = [
    path("", DocumentListCreateView.as_view(), name="document-list"),
    path("verify/", DocumentGlobalVerifyView.as_view(), name="document-verify-global"),
    path("suspects/", DocumentSuspectListView.as_view(), name="document-suspects"),
    path("<uuid:pk>/", DocumentDetailView.as_view(), name="document-detail"),
    path("<uuid:pk>/verify/", DocumentVerifyView.as_view(), name="document-verify"),
]
