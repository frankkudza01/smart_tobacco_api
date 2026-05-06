import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("organizations", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DataSubjectRequest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("request_type", models.CharField(choices=[("export", "Export my data"), ("delete", "Request erasure")], max_length=16)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("processing", "Processing"), ("completed", "Completed"), ("rejected", "Rejected")], db_index=True, default="pending", max_length=16)),
                ("notes", models.TextField(blank=True, default="")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="privacy_requests", to="organizations.organization")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="privacy_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "privacy_controls_data_subject_request", "ordering": ["-created_at"]},
        ),
    ]
