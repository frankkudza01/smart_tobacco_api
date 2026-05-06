from django.urls import path

from apps.organizations.views import (
    MembershipDetailView,
    MembershipListCreateView,
    OrganizationDetailView,
    OrganizationListCreateView,
)

urlpatterns = [
    path("", OrganizationListCreateView.as_view(), name="organization-list"),
    path("<uuid:pk>/", OrganizationDetailView.as_view(), name="organization-detail"),
    path("memberships/", MembershipListCreateView.as_view(), name="membership-list"),
    path("memberships/<uuid:pk>/", MembershipDetailView.as_view(), name="membership-detail"),
]
