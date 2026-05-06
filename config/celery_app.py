import os
import sys

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("tobacco_platform")
app.config_from_object("django.conf:settings", namespace="CELERY")

# Windows: prefork uses billiard multiprocessing + semaphores that often fail with
# PermissionError (WinError 5). Solo pool runs tasks in the worker process (no child pool).
if sys.platform == "win32":
    app.conf.update(
        worker_pool="solo",
        worker_concurrency=1,
        task_soft_time_limit=None,  # soft limits need SIGUSR1 (Unix-only)
    )

app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
