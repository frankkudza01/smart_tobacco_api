from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("seasons", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="season",
            name="farmer_accepted",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="season",
            name="farmer_accepted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
