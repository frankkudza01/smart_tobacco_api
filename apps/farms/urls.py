from django.urls import path

from apps.farms.views import (
    FarmDetailView,
    FarmGeofenceLocationCheckView,
    FarmGisVerificationView,
    FarmListCreateView,
)

urlpatterns = [
    path("", FarmListCreateView.as_view(), name="farm-list"),
    path("<uuid:pk>/gis-verification/", FarmGisVerificationView.as_view(), name="farm-gis-verification"),
    path("<uuid:pk>/location-check/", FarmGeofenceLocationCheckView.as_view(), name="farm-location-check"),
    path("<uuid:pk>/", FarmDetailView.as_view(), name="farm-detail"),
]
