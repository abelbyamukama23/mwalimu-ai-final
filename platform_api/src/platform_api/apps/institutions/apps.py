"""Django app configuration for institutions."""

from django.apps import AppConfig


class InstitutionsConfig(AppConfig):
    """Institutions app configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "platform_api.apps.institutions"
    label = "institutions"
