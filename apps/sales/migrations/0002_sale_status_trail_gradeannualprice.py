import uuid

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="GradeAnnualPrice",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("grade", models.CharField(db_index=True, max_length=20)),
                ("year", models.PositiveIntegerField(db_index=True)),
                ("price_per_kg", models.DecimalField(decimal_places=2, max_digits=10)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("notes", models.TextField(blank=True, default="")),
            ],
            options={
                "db_table": "sales_grade_annual_price",
                "ordering": ["-year", "grade"],
                "unique_together": {("grade", "year")},
            },
        ),
        migrations.AddField(
            model_name="sale",
            name="accepted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sale",
            name="ai_pricing_note",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="sale",
            name="annual_price_year",
            field=models.PositiveIntegerField(default=django.utils.timezone.now().year),
        ),
        migrations.AddField(
            model_name="sale",
            name="bought_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sale",
            name="declined_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sale",
            name="grading_trail",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="sale",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("ACCEPTED", "Accepted"),
                    ("DECLINED", "Declined"),
                    ("BOUGHT", "Bought"),
                ],
                db_index=True,
                default="PENDING",
                max_length=20,
            ),
        ),
    ]
