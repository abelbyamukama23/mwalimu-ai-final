"""Django app configuration for resources."""

from django.apps import AppConfig


class ResourcesConfig(AppConfig):
    """Configuration for the resources app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "platform_api.apps.resources"
    label = "resources"
