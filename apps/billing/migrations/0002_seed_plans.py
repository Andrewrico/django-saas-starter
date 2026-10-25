from django.db import migrations

PLANS = [
    {"slug": "free", "name": "Free", "limits": {"max_items": 20}, "sort_order": 0},
    # Not purchasable until you set a Stripe Price id in the admin (docs/billing.md).
    {"slug": "pro", "name": "Pro", "limits": {"max_items": 1000}, "sort_order": 10},
]


def seed(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for plan in PLANS:
        Plan.objects.get_or_create(slug=plan["slug"], defaults=plan)


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
