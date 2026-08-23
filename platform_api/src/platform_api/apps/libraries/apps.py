"""Django app configuration for libraries."""

from django.apps import AppConfig


class LibrariesConfig(AppConfig):
    """Configuration for the libraries app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "platform_api.apps.libraries"
    label = "libraries"
