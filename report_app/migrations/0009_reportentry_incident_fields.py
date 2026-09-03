from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("report_app", "0008_projectplanmarker"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportentry",
            name="incident_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reportentry",
            name="responsible_company",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="reportentry",
            name="plan_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reportentry",
            name="plan_x",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reportentry",
            name="plan_y",
            field=models.FloatField(blank=True, null=True),
        ),
    ]