from django.urls import path

from apps.sync.views import (
    BatchSyncView,
    DocumentsBatchSyncView,
    EventsBatchSyncView,
    SyncChangesView,
)

urlpatterns = [
    path("", BatchSyncView.as_view(), name="batch-sync"),
    path("events/batch/", EventsBatchSyncView.as_view(), name="sync-events-batch"),
    path("documents/batch/", DocumentsBatchSyncView.as_view(), name="sync-documents-batch"),
    path("changes/", SyncChangesView.as_view(), name="sync-changes"),
]
