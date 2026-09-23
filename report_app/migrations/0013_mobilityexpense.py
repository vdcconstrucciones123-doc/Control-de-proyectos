import report_app.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("report_app", "0012_alter_entryimage_image_alter_projectplan_file_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="MobilityExpense",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(verbose_name="fecha")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10, verbose_name="monto")),
                ("transport", models.CharField(blank=True, max_length=80, verbose_name="movilidad")),
                ("origin", models.CharField(blank=True, max_length=120, verbose_name="origen")),
                ("destination", models.CharField(blank=True, max_length=120, verbose_name="destino")),
                ("status", models.CharField(choices=[("pendiente", "Pendiente"), ("pagado", "Pagado")], default="pendiente", max_length=20, verbose_name="estado")),
                ("receipt", models.FileField(blank=True, null=True, upload_to=report_app.models.mobility_receipt_upload_to, verbose_name="evidencia")),
                ("notes", models.CharField(blank=True, max_length=250, verbose_name="observación")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["date", "id"]},
        ),
    ]