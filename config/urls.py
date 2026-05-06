from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.disputes.views import DisputeAnalyticsSummaryView
from apps.whatsapp.views import WhatsAppWebhookView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("whatsapp/webhook/", WhatsAppWebhookView.as_view(), name="whatsapp-webhook-root"),
    path("api/v1/auth/", include("apps.accounts.urls_auth")),
    path("api/v1/users/", include("apps.accounts.urls_users")),
    path("api/v1/organizations/", include("apps.organizations.urls")),
    path("api/v1/farms/", include("apps.farms.urls")),
    path("api/v1/seasons/", include("apps.seasons.urls")),
    path("api/v1/lots/", include("apps.lots.urls")),
    path("api/v1/trace-events/", include("apps.traceability.urls")),
    path("api/v1/documents/", include("apps.documents.urls")),
    path("api/v1/grading/", include("apps.grading.urls")),
    path("api/v1/weather/", include("apps.weather.urls")),
    path("api/v1/tobacco-monitoring/", include("apps.tobacco_monitoring.urls")),
    path("api/v1/sales/", include("apps.sales.urls")),
    path("api/v1/settlements/", include("apps.settlements.urls")),
    path("api/v1/disputes/", include("apps.disputes.urls")),
    path("api/v1/provenance/", include("apps.provenance.urls")),
    path("api/v1/sync/", include("apps.sync.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
    path("api/v1/devices/", include("apps.notifications.urls_devices")),
    path("api/v1/ai/", include("apps.ai_intelligence.urls")),
    path("api/v1/blockchain/", include("apps.blockchain.urls")),
    path("api/v1/whatsapp/", include("apps.whatsapp.urls")),
    path("api/v1/analytics/disputes/summary/", DisputeAnalyticsSummaryView.as_view(), name="analytics-disputes-summary"),
    path("api/v1/", include("apps.worldready.urls")),
    path("api/v1/", include("apps.ml_monitoring.urls")),
    path("api/v1/", include("apps.privacy_controls.urls")),
    path("api/v1/", include("apps.common.urls")),
    # OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns

admin.site.site_header = "Zimbabwe Tobacco Supply Chain Admin"
admin.site.site_title = "Tobacco Platform"
admin.site.index_title = "Administration"
