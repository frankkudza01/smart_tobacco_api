from django.apps import AppConfig


class MlMonitoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ml_monitoring"
    verbose_name = "ML monitoring & drift"
