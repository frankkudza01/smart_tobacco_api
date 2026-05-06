from django.contrib import admin

from apps.organizations.models import Organization, OrganizationMembership


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "org_type", "registration_number", "is_active", "created_at")
    list_filter = ("is_active", "org_type")
    search_fields = ("name", "registration_number")


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "is_primary", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("user__email", "organization__name")
    raw_id_fields = ("user", "organization")
