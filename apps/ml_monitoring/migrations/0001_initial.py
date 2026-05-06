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
            name="ModelRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("model_type", models.CharField(choices=[("yield", "Yield forecast"), ("price", "Price forecast"), ("anomaly", "Anomaly"), ("duplicate", "Near-duplicate")], db_index=True, max_length=32)),
                ("model_version", models.CharField(db_index=True, max_length=64)),
                ("trained_at", models.DateTimeField(blank=True, null=True)),
                ("metrics_json", models.JSONField(blank=True, default=dict)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="model_runs_created", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="model_runs", to="organizations.organization")),
            ],
            options={"db_table": "ml_monitoring_model_run", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="DailyMetrics",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("date", models.DateField(db_index=True)),
                ("mape_yield", models.DecimalField(blank=True, decimal_places=4, max_digits=8, null=True)),
                ("mape_price", models.DecimalField(blank=True, decimal_places=4, max_digits=8, null=True)),
                ("auroc_anomaly", models.DecimalField(blank=True, decimal_places=4, max_digits=8, null=True)),
                ("precision_dup", models.DecimalField(blank=True, decimal_places=4, max_digits=8, null=True)),
                ("recall_dup", models.DecimalField(blank=True, decimal_places=4, max_digits=8, null=True)),
                ("alert_volume", models.PositiveIntegerField(default=0)),
                ("false_positive_rate", models.DecimalField(blank=True, decimal_places=4, max_digits=8, null=True)),
                ("extra_json", models.JSONField(blank=True, default=dict)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="daily_metrics", to="organizations.organization")),
            ],
            options={"db_table": "ml_monitoring_daily_metrics", "ordering": ["-date"]},
        ),
        migrations.CreateModel(
            name="DriftMetrics",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("date", models.DateField(db_index=True)),
                ("feature_drift_json", models.JSONField(blank=True, default=dict)),
                ("outcome_drift_json", models.JSONField(blank=True, default=dict)),
                ("triggered", models.BooleanField(db_index=True, default=False)),
                ("reason", models.CharField(blank=True, default="", max_length=500)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="drift_metrics", to="organizations.organization")),
            ],
            options={"db_table": "ml_monitoring_drift_metrics", "ordering": ["-date"]},
        ),
        migrations.AddIndex(model_name="modelrun", index=models.Index(fields=["organization", "model_type"], name="ml_monitorin_organiz_idx")),
        migrations.AlterUniqueTogether(name="dailymetrics", unique_together={("organization", "date")}),
        migrations.AlterUniqueTogether(name="driftmetrics", unique_together={("organization", "date")}),
        migrations.AddIndex(model_name="driftmetrics", index=models.Index(fields=["organization", "triggered"], name="ml_monitorin_organiz_0_idx")),
    ]
