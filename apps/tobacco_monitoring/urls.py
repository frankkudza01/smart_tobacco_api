from django.urls import path

from apps.tobacco_monitoring import views

urlpatterns = [
    path(
        "integration-check/",
        views.AgroMonitoringIntegrationCheckView.as_view(),
        name="tobacco-agro-integration-check",
    ),
    path("polygons/", views.TobaccoFieldPolygonListCreateView.as_view(), name="tobacco-polygon-list"),
    path("polygons/<uuid:pk>/", views.TobaccoFieldPolygonDetailView.as_view(), name="tobacco-polygon-detail"),
    path(
        "polygons/<uuid:polygon_pk>/observations/",
        views.PolygonObservationListView.as_view(),
        name="tobacco-polygon-observations",
    ),
    path(
        "polygons/<uuid:polygon_pk>/latest-status/",
        views.PolygonLatestStatusView.as_view(),
        name="tobacco-polygon-latest-status",
    ),
    path(
        "polygons/<uuid:polygon_pk>/poll/",
        views.PolygonPollNowView.as_view(),
        name="tobacco-polygon-poll",
    ),
    path("stress-events/", views.CropStressEventListView.as_view(), name="tobacco-stress-list"),
    path("stress-events/<uuid:pk>/", views.CropStressEventDetailView.as_view(), name="tobacco-stress-detail"),
    path(
        "summaries/buyer/",
        views.BuyerMonitoringSummaryView.as_view(),
        name="tobacco-summary-buyer",
    ),
    path(
        "summaries/regional/",
        views.RegionalMonitoringSummaryView.as_view(),
        name="tobacco-summary-regional",
    ),
    path(
        "planting-verifications/",
        views.PlantingVerificationListCreateView.as_view(),
        name="tobacco-planting-verification-list",
    ),
]
