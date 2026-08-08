from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReportProject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("company_name", models.CharField(default="VDC CONSTRUCCIONES SAC", max_length=200)),
                ("project_name", models.CharField(blank=True, max_length=200)),
                ("project_location", models.CharField(blank=True, max_length=200)),
                ("slug", models.SlugField(blank=True, max_length=220, unique=True)),
                ("report_title", models.CharField(default="REPORTE FOTOGRÁFICO DE OBRA", max_length=200)),
                ("for_whom", models.CharField(blank=True, max_length=200)),
                ("from_whom", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="owned_projects", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["project_name", "id"]},
        ),
        migrations.CreateModel(
            name="ProjectReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("report_type", models.CharField(choices=[("avances", "Reporte de avances"), ("incidencia", "Reporte de incidencia")], default="avances", max_length=20)),
                ("title", models.CharField(default="REPORTE FOTOGRÁFICO DE OBRA", max_length=200)),
                ("week", models.CharField(blank=True, max_length=50)),
                ("report_date", models.DateField(blank=True, null=True)),
                ("labor_date_from", models.DateField(blank=True, null=True)),
                ("labor_date_to", models.DateField(blank=True, null=True)),
                ("for_whom", models.CharField(blank=True, max_length=200)),
                ("from_whom", models.CharField(blank=True, max_length=200)),
                ("objective_text", models.TextField(blank=True)),
                ("analysis_text", models.TextField(blank=True)),
                ("conclusion_text", models.TextField(blank=True)),
                ("recommendation_text", models.TextField(blank=True)),
                ("conclusion_items", models.JSONField(blank=True, default=list)),
                ("recommendation_items", models.JSONField(blank=True, default=list)),
                ("cover_image", models.FileField(blank=True, null=True, upload_to="report_covers/")),
                ("auto_merge_dup", models.BooleanField(default=False)),
                ("combine_by_status", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reports", to="report_app.reportproject")),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="ReportFront",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("report", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fronts", to="report_app.projectreport")),
            ],
            options={"ordering": ["sort_order", "id"]},
        ),
        migrations.CreateModel(
            name="ReportEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(max_length=50)),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("front", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entries", to="report_app.reportfront")),
                ("report", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entries", to="report_app.projectreport")),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="EntryImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.FileField(upload_to="report_entries/")),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("entry", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="images", to="report_app.reportentry")),
            ],
            options={"ordering": ["sort_order", "id"]},
        ),
        migrations.CreateModel(
            name="ProjectMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("viewer", "Lector"), ("editor", "Editor"), ("admin", "Administrador")], default="viewer", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="report_app.reportproject")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="project_memberships", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["project_id", "user__username"], "unique_together": {("project", "user")}},
        ),
    ]