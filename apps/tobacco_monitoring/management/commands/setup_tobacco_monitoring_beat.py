"""
Ensure django-celery-beat has the tobacco satellite poll periodic task.

Safe to run multiple times (idempotent). Use when migrations were skipped or
after changing cron defaults in admin.
"""

from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask

TASK = "apps.tobacco_monitoring.tasks.poll_all_active_polygons_task"
TASK_NAME = "tobacco-monitoring-satellite-poll"


class Command(BaseCommand):
    help = "Create or update the Celery Beat schedule for tobacco satellite polling (daily 06:00 Africa/Harare)."

    def handle(self, *args, **options):
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute="0",
            hour="6",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            timezone="Africa/Harare",
        )
        task, created = PeriodicTask.objects.get_or_create(
            name=TASK_NAME,
            defaults={
                "task": TASK,
                "crontab": schedule,
                "enabled": True,
                "kwargs": "{}",
                "args": "[]",
                "headers": "{}",
            },
        )
        if not created:
            task.task = TASK
            task.crontab = schedule
            task.enabled = True
            task.save(update_fields=["task", "crontab", "enabled", "date_changed"])
            self.stdout.write(self.style.SUCCESS(f"Updated periodic task: {TASK_NAME}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Created periodic task: {TASK_NAME}"))
