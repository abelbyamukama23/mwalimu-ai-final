"""Context application configuration."""

from django.apps import AppConfig


class ContextConfig(AppConfig):
    """Django app configuration for Mwalimu context domain."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "platform_api.apps.context"
    verbose_name = "Context"
