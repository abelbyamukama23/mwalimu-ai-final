"""Data migration to seed default platform connectors."""

from django.db import migrations
from platform_api.apps.connectors.defaults import DEFAULT_CONNECTORS


def seed_connectors(apps, schema_editor):
    """Seed initial catalog of platform connectors."""
    Connector = apps.get_model("connectors", "Connector")
    for item in DEFAULT_CONNECTORS:
        Connector.objects.update_or_create(
            slug=item["slug"],
            defaults={
                "id": item["id"],
                "name": item["name"],
                "description": item["description"],
                "connector_type": item["connector_type"],
                "auth_type": item["auth_type"],
                "config_schema": item["config_schema"],
                "auth_schema": item["auth_schema"],
                "is_active": item["is_active"],
            },
        )


def unseed_connectors(apps, schema_editor):
    """Rollback connector seeds."""
    Connector = apps.get_model("connectors", "Connector")
    slugs = [item["slug"] for item in DEFAULT_CONNECTORS]
    Connector.objects.filter(slug__in=slugs).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("connectors", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_connectors, reverse_code=unseed_connectors),
    ]
