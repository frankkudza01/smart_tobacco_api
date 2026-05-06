from django.urls import path

from apps.grading.views import GradeCatalogView, GradeRecordDetailView, GradeRecordListCreateView, GradeSuggestView

urlpatterns = [
    path("", GradeRecordListCreateView.as_view(), name="grading-list"),
    path("catalog/", GradeCatalogView.as_view(), name="grading-catalog"),
    path("suggest/", GradeSuggestView.as_view(), name="grading-suggest"),
    path("<uuid:pk>/", GradeRecordDetailView.as_view(), name="grading-detail"),
]
