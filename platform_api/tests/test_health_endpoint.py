"""Tests for Platform API unauthenticated health check endpoint."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_check_endpoint_returns_200_without_auth() -> None:
    """GET /health/ returns 200 and expected status without authentication."""
    client = APIClient()
    response = client.get("/health/")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "mwalimu-platform-api"


@pytest.mark.django_db
def test_health_check_endpoint_without_trailing_slash() -> None:
    """GET /health also returns 200 without authentication."""
    client = APIClient()
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "mwalimu-platform-api"


@pytest.mark.django_db
def test_health_check_rejects_post_requests() -> None:
    """POST /health/ is rejected (405 Method Not Allowed)."""
    client = APIClient()
    response = client.post("/health/")

    assert response.status_code == 405
