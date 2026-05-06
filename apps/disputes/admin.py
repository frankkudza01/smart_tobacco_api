from django.contrib import admin

from apps.disputes.models import Dispute, DisputeComment


class DisputeCommentInline(admin.TabularInline):
    model = DisputeComment
    extra = 0
    raw_id_fields = ("author",)


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "raised_by", "lot", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "description")
    raw_id_fields = ("lot", "sale", "raised_by", "assigned_to")
    inlines = [DisputeCommentInline]
