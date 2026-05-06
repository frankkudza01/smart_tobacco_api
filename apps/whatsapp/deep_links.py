from django.conf import settings


def app_scheme() -> str:
    return getattr(settings, "APP_DEEP_LINK_SCHEME", "app")


def anomaly_link(alert_id) -> str:
    return f"{app_scheme()}://anomaly/{alert_id}"


def forecast_link(kind: str = "yield", scope: str = "my") -> str:
    return f"{app_scheme()}://forecast/{kind}?scope={scope}"
