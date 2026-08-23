"""Django app configuration for users."""

from django.apps import AppConfig


class UsersConfig(AppConfig):
    """Users app configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "platform_api.apps.users"
    label = "users"
