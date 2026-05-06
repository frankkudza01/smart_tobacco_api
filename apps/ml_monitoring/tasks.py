from celery import shared_task
from django.utils import timezone

from apps.ml_monitoring.services.rollup import rollup_daily_metrics_for_org
from apps.organizations.models import Organization


@shared_task(name="ml_monitoring.rollup_all_orgs_daily")
def rollup_all_orgs_daily():
    for org in Organization.objects.filter(is_active=True):
        try:
            rollup_daily_metrics_for_org(org, on_date=timezone.now().date())
        except Exception:
            pass
    return "ok"


@shared_task(name="ml_monitoring.rollup_org_daily")
def rollup_org_daily(org_id: str):
    org = Organization.objects.get(id=org_id)
    rollup_daily_metrics_for_org(org, on_date=timezone.now().date())
    return org_id
