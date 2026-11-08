from django.db import migrations


def set_free_label(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(slug="free", price_label="").update(price_label="$0")


class Migration(migrations.Migration):
    dependencies = [("billing", "0003_plan_price_label")]
    operations = [migrations.RunPython(set_free_label, migrations.RunPython.noop)]
