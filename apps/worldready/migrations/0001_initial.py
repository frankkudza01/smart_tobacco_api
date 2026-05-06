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
            name="UserPreference",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("preferred_language", models.CharField(choices=[("en", "English"), ("sn", "Shona"), ("nd", "Ndebele")], default="en", max_length=8)),
                ("literacy_mode", models.CharField(choices=[("normal", "Normal"), ("guided", "Guided (low-literacy)")], default="normal", max_length=16)),
                ("voice_mode_enabled", models.BooleanField(default=False)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="user_preferences", to="organizations.organization")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ux_preferences", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "worldready_user_preference"},
        ),
        migrations.CreateModel(
            name="TranslationOverride",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("key", models.CharField(db_index=True, max_length=200)),
                ("locale", models.CharField(db_index=True, max_length=16)),
                ("value", models.TextField()),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="translation_overrides", to="organizations.organization")),
            ],
            options={"db_table": "worldready_translation_override"},
        ),
        migrations.CreateModel(
            name="TaskCompletionLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("channel", models.CharField(choices=[("flutter", "Flutter"), ("whatsapp", "WhatsApp")], db_index=True, max_length=20)),
                ("task_name", models.CharField(db_index=True, max_length=120)),
                ("started_at", models.DateTimeField(db_index=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("success", models.BooleanField(default=False)),
                ("error_code", models.CharField(blank=True, default="", max_length=64)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="task_completion_logs", to="organizations.organization")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="task_completion_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "worldready_task_completion_log", "ordering": ["-started_at"]},
        ),
        migrations.CreateModel(
            name="SupportRequestLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("channel", models.CharField(choices=[("flutter", "Flutter"), ("whatsapp", "WhatsApp")], db_index=True, max_length=20)),
                ("request_type", models.CharField(db_index=True, max_length=64)),
                ("body_preview", models.CharField(blank=True, default="", max_length=240)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="support_request_logs", to="organizations.organization")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="support_request_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "worldready_support_request_log", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="SusSurveyResponse",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("channel", models.CharField(blank=True, choices=[("flutter", "Flutter"), ("whatsapp", "WhatsApp")], default="", max_length=20)),
                ("scores_json", models.JSONField(blank=True, default=dict)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sus_survey_responses", to="organizations.organization")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sus_survey_responses", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "worldready_sus_survey_response", "ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="userpreference", index=models.Index(fields=["organization", "user"], name="worldready__organiz_idx")),
        migrations.AlterUniqueTogether(name="userpreference", unique_together={("user", "organization")}),
        migrations.AlterUniqueTogether(name="translationoverride", unique_together={("organization", "key", "locale")}),
        migrations.AddIndex(model_name="taskcompletionlog", index=models.Index(fields=["organization", "channel", "task_name"], name="worldready__organiz_0_idx")),
    ]
