"""Django app configuration for the document processing and knowledge indexing app."""

from django.apps import AppConfig


class ProcessingConfig(AppConfig):
    """Configuration for the processing app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "platform_api.apps.processing"
    label = "processing"
    verbose_name = "Document Processing"
