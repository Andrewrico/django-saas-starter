import apps.example.models
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("example", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="Attachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to=apps.example.models.attachment_path)),
                ("original_filename", models.CharField(max_length=255)),
                ("size", models.PositiveBigIntegerField()),
                ("content_type", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="example.project",
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-id"]},
        )
    ]
