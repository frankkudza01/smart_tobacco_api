from django.urls import path

from apps.seasons.views import SeasonAcceptView, SeasonDetailView, SeasonListCreateView

urlpatterns = [
    path("", SeasonListCreateView.as_view(), name="season-list"),
    path("<uuid:pk>/", SeasonDetailView.as_view(), name="season-detail"),
    path("<uuid:pk>/accept/", SeasonAcceptView.as_view(), name="season-accept"),
]
