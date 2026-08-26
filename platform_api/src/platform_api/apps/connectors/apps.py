"""App configuration for the connectors application."""

from django.apps import AppConfig


class ConnectorsConfig(AppConfig):
    """Configuration for connectors app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "platform_api.apps.connectors"
    verbose_name = "Connectors"
