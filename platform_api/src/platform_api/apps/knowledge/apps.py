"""App configuration for the knowledge retrieval gateway."""

from django.apps import AppConfig


class KnowledgeConfig(AppConfig):
    """Knowledge app configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "platform_api.apps.knowledge"
    verbose_name = "Knowledge Retrieval Gateway"
