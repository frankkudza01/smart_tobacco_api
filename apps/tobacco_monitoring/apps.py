from django.apps import AppConfig


class TobaccoMonitoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tobacco_monitoring"
    verbose_name = "Tobacco satellite monitoring"

    def ready(self):
        from apps.tobacco_monitoring import signals  # noqa: F401
