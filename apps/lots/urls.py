from django.urls import path

from apps.lots.views import LotDetailView, LotFarmSummaryView, LotListCreateView

urlpatterns = [
    path("", LotListCreateView.as_view(), name="lot-list"),
    path("summary/", LotFarmSummaryView.as_view(), name="lot-farm-summary"),
    # Accept UUID primary key or human-readable `lot_number` (e.g. ZW-2026-0412).
    path("<str:pk>/", LotDetailView.as_view(), name="lot-detail"),
]
