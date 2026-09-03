from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("report_app", "0005_reportproject_project_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="profile_image",
            field=models.FileField(blank=True, null=True, upload_to="profile_images/"),
        ),
    ]