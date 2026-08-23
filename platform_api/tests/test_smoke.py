"""Dependency and import smoke tests for the Platform API foundation."""

import sys

import celery
import django
import httpx
import psycopg
import pydantic
import redis
from pgvector.django import VectorExtension
from rest_framework import VERSION as DRF_VERSION


def test_python_version() -> None:
    """Python 3.13 is required."""
    assert sys.version_info[:2] == (3, 13)


def test_django_version() -> None:
    """Django 6.0.x is required."""
    assert django.VERSION[:2] == (6, 0)


def test_drf_import() -> None:
    """Django REST Framework is importable."""
    assert DRF_VERSION is not None
    assert DRF_VERSION.startswith("3.")


def test_psycopg_import() -> None:
    """psycopg 3 is importable."""
    assert psycopg.__version__.startswith("3.")


def test_pgvector_import() -> None:
    """pgvector Django integration is importable."""
    assert VectorExtension is not None


def test_celery_import() -> None:
    """Celery is importable."""
    assert celery.__version__ is not None


def test_redis_import() -> None:
    """Redis client is importable."""
    assert redis.__version__ is not None


def test_httpx_import() -> None:
    """HTTPX is importable."""
    assert httpx.__version__ is not None


def test_pydantic_import() -> None:
    """Pydantic v2 is importable."""
    assert pydantic.VERSION.startswith("2.")
