from django.apps import AppConfig


class AiIntelligenceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai_intelligence"
    verbose_name = "AI Intelligence (forecasting & anomalies)"

    def ready(self):
        import apps.ai_intelligence.signals  # noqa: F401
