# Idempotent django-celery-beat entry for tobacco satellite polling.

from django.db import migrations

TASK = "apps.tobacco_monitoring.tasks.poll_all_active_polygons_task"
TASK_NAME = "tobacco-monitoring-satellite-poll"


def forwards(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="6",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="Africa/Harare",
    )
    PeriodicTask.objects.get_or_create(
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


def backwards(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("django_celery_beat", "0001_initial"),
        ("tobacco_monitoring", "0001_initial_tobacco_monitoring"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
