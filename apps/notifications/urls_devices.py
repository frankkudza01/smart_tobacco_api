from django.urls import path

from apps.notifications.views import DeviceRegisterView

urlpatterns = [
    path("register/", DeviceRegisterView.as_view(), name="device-register"),
]
