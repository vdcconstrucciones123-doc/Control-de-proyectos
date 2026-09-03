from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("report_app", "0004_userprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportproject",
            name="project_image",
            field=models.FileField(blank=True, null=True, upload_to="project_images/"),
        ),
    ]