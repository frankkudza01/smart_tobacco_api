from django.urls import path

from apps.disputes.views import (
    DisputeCasePacketView,
    DisputeCommentNestedCreateView,
    DisputeDetailView,
    DisputeLabelView,
    DisputeListCreateView,
    DisputeResolveView,
    DisputeRespondView,
)

urlpatterns = [
    path("", DisputeListCreateView.as_view(), name="dispute-list"),
    path("<uuid:pk>/", DisputeDetailView.as_view(), name="dispute-detail"),
    path("<uuid:pk>/comments/", DisputeCommentNestedCreateView.as_view(), name="dispute-comment-create"),
    path("<uuid:pk>/respond/", DisputeRespondView.as_view(), name="dispute-respond"),
    path("<uuid:pk>/label/", DisputeLabelView.as_view(), name="dispute-label"),
    path("<uuid:pk>/resolve/", DisputeResolveView.as_view(), name="dispute-resolve"),
    path("<uuid:pk>/case-packet/", DisputeCasePacketView.as_view(), name="dispute-case-packet"),
]
