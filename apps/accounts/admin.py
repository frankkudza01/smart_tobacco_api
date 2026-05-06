from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import AdminProfile, AuditorProfile, BuyerProfile, FarmerProfile, OTPChallengeLog, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "first_name", "last_name", "role", "is_active", "date_joined")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("-date_joined",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal", {"fields": ("first_name", "last_name", "phone_number")}),
        ("Role", {"fields": ("role",)}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "first_name", "last_name", "role", "password1", "password2")}),
    )


@admin.register(FarmerProfile)
class FarmerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "national_id", "district")
    search_fields = ("user__email", "national_id")


@admin.register(BuyerProfile)
class BuyerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "company_name", "license_number")
    search_fields = ("user__email", "company_name")


@admin.register(AuditorProfile)
class AuditorProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "badge_number")


@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "department")


@admin.register(OTPChallengeLog)
class OTPChallengeLogAdmin(admin.ModelAdmin):
    list_display = ("phone_number", "user", "purpose", "status", "delivery_channel", "created_at")
    list_filter = ("status", "purpose", "delivery_channel")
    search_fields = ("phone_number", "user__email")
    raw_id_fields = ("user",)
    readonly_fields = ("phone_number", "purpose", "status", "expires_at", "verified_at", "ip_address")
