from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("report_app", "0007_projectplan")]
    operations = [
        migrations.CreateModel(
            name="ProjectPlanMarker",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("page", models.PositiveIntegerField(default=1)),
                ("x", models.FloatField()),
                ("y", models.FloatField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="markers", to="report_app.projectplan")),
            ],
            options={"ordering": ["page", "created_at", "id"]},
        ),
    ]