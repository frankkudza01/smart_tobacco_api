from django.urls import path

from apps.settlements.views import SettlementDetailView, SettlementListCreateView

urlpatterns = [
    path("", SettlementListCreateView.as_view(), name="settlement-list"),
    path("<uuid:pk>/", SettlementDetailView.as_view(), name="settlement-detail"),
]
