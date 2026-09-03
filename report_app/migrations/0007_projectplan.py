from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("report_app", "0006_userprofile_profile_image"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(blank=True, max_length=200)),
                ("file", models.FileField(upload_to="project_plans/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="plans",
                        to="report_app.reportproject",
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
    ]