"""Celery configuration for the Mwalimu Platform API."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "platform_api.settings")

app = Celery("platform_api")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
