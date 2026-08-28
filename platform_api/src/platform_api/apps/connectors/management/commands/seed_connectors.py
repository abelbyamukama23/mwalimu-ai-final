"""Management command to seed or refresh default platform connectors."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from platform_api.apps.connectors.defaults import DEFAULT_CONNECTORS
from platform_api.apps.connectors.models import Connector


class Command(BaseCommand):
    """Seed or update platform connectors catalog in the database."""

    help = "Seed platform connector catalog (Web Crawler, Google Drive, Notion, S3, File System)"

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute command."""
        self.stdout.write("Seeding default platform connectors...")
        count = 0
        for item in DEFAULT_CONNECTORS:
            connector, created = Connector.objects.update_or_create(
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
            action = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(
                    f"  {action} connector '{connector.name}' ({connector.connector_type})"
                )
            )
            count += 1

        self.stdout.write(
            self.style.SUCCESS(f"Successfully seeded {count} platform connectors.")
        )
