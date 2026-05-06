from django.urls import path

from apps.sales.views import SaleDetailView, SaleListCreateView, SaleStatusActionView

urlpatterns = [
    path("", SaleListCreateView.as_view(), name="sale-list"),
    path("<uuid:pk>/", SaleDetailView.as_view(), name="sale-detail"),
    path("<uuid:pk>/<str:action>/", SaleStatusActionView.as_view(), name="sale-status-action"),
]
