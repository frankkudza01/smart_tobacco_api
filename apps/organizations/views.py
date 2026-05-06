from rest_framework import generics

from apps.common.permissions import IsAdminOrAuditor, IsSystemAdmin
from apps.organizations.models import Organization, OrganizationMembership
from apps.organizations.serializers import OrganizationMembershipSerializer, OrganizationSerializer


class OrganizationListCreateView(generics.ListCreateAPIView):
    serializer_class = OrganizationSerializer
    permission_classes = [IsSystemAdmin]
    filterset_fields = ["is_active", "org_type"]
    search_fields = ["name", "registration_number"]

    def get_queryset(self):
        return Organization.objects.all()


class OrganizationDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = OrganizationSerializer
    permission_classes = [IsAdminOrAuditor]
    queryset = Organization.objects.all()
    lookup_field = "pk"


class MembershipListCreateView(generics.ListCreateAPIView):
    serializer_class = OrganizationMembershipSerializer
    permission_classes = [IsSystemAdmin]
    filterset_fields = ["organization", "role", "is_active"]

    def get_queryset(self):
        return OrganizationMembership.objects.select_related("user", "organization").all()


class MembershipDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = OrganizationMembershipSerializer
    permission_classes = [IsSystemAdmin]
    queryset = OrganizationMembership.objects.select_related("user", "organization")
    lookup_field = "pk"
