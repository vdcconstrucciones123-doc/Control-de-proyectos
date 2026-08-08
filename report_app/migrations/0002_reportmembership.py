from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("report_app", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReportMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("viewer", "Lector"), ("editor", "Editor"), ("admin", "Administrador")], default="viewer", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("report", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="report_app.projectreport")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="report_memberships", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["report_id", "user__username"], "unique_together": {("report", "user")}},
        ),
    ]
