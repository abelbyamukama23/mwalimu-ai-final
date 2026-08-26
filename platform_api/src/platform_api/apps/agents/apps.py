"""Django app configuration for agents."""

from django.apps import AppConfig


class AgentsConfig(AppConfig):
    """Configuration for the agents app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "platform_api.apps.agents"
    label = "agents"
    verbose_name = "Agent Sessions & Runs"
