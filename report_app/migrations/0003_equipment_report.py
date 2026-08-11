from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("report_app", "0002_reportmembership"),
    ]

    operations = [
        migrations.AlterField(
            model_name="projectreport",
            name="report_type",
            field=models.CharField(
                choices=[
                    ("avances", "Reporte de avances"),
                    ("incidencia", "Reporte de incidencia"),
                    ("equipos", "Recepción y entrega de equipos"),
                ],
                default="avances",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="reportentry",
            name="building_location",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="reportentry",
            name="item_name",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="reportentry",
            name="quantity",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
