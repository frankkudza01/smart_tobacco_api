from django.urls import path

from apps.whatsapp.views import WhatsAppDeliveryStatusView, WhatsAppWebhookView

urlpatterns = [
    path("webhook/", WhatsAppWebhookView.as_view(), name="whatsapp-webhook"),
    path("status/", WhatsAppDeliveryStatusView.as_view(), name="whatsapp-delivery-status"),
]
