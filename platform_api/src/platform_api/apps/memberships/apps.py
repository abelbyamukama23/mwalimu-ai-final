"""Django app configuration for memberships."""

from django.apps import AppConfig


class MembershipsConfig(AppConfig):
    """Memberships app configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "platform_api.apps.memberships"
    label = "memberships"
