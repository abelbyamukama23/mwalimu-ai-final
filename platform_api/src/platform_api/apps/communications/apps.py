"""App configuration for communications."""

from django.apps import AppConfig


class CommunicationsConfig(AppConfig):
    """Communications app configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "platform_api.apps.communications"
    verbose_name = "Communications"
