"""Tests for cookie-based JWT authentication.

Contract under test:
- Login returns only `{access}` and sets the refresh token as an HttpOnly cookie.
- Refresh reads refresh token from cookie (never body) and is CSRF-protected.
- Logout clears the refresh cookie (CSRF-protected).
- CORS reflects the allowed origin with credentials and permits the CSRF header.
"""

import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

LOGIN_URL = reverse("token_obtain_pair")
REFRESH_URL = reverse("token_refresh")
LOGOUT_URL = reverse("auth_logout")
ME_URL = reverse("current_user")

CREDENTIALS = {"email": "user.a@example.com", "password": "password-a-123"}


def _login(client: APIClient) -> dict:
    """Log in and return the parsed response data."""
    return client.post(LOGIN_URL, CREDENTIALS, format="json")


def _csrf(client: APIClient) -> str:
    value = client.cookies.get("csrftoken").value
    assert value, "csrftoken cookie was not established by login"
    return value


def _csrf_client() -> APIClient:
    """A client that enforces CSRF like a real browser (DRF bypasses it otherwise)."""
    return APIClient(enforce_csrf_checks=True)


# --- Login ---------------------------------------------------------------


@pytest.mark.django_db
def test_login_returns_access_only(user_a, api_client: APIClient) -> None:
    response = _login(api_client)

    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert "refresh" not in response.data
    assert isinstance(response.data["access"], str)


@pytest.mark.django_db
def test_login_sets_refresh_cookie_attributes(user_a, api_client: APIClient) -> None:
    response = _login(api_client)

    morsel = response.cookies.get(settings.REFRESH_COOKIE_NAME)
    assert morsel is not None
    output = morsel.output().lower()
    assert "httponly" in output
    assert "samesite=lax" in output
    assert f"path={settings.REFRESH_COOKIE_PATH}" in output


@pytest.mark.django_db
def test_login_sets_secure_cookie_when_configured(user_a, api_client, settings) -> None:
    settings.REFRESH_COOKIE_SECURE = True
    response = _login(api_client)
    morsel = response.cookies.get(settings.REFRESH_COOKIE_NAME)
    assert morsel is not None
    assert "secure" in morsel.output().lower()


@pytest.mark.django_db
def test_login_establishes_csrf_cookie(user_a, api_client: APIClient) -> None:
    _login(api_client)
    assert api_client.cookies.get("csrftoken") is not None


@pytest.mark.django_db
def test_login_invalid_password(api_client: APIClient) -> None:
    response = api_client.post(
        LOGIN_URL,
        {"email": "user.a@example.com", "password": "wrong-password"},
        format="json",
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "access" not in response.data
    assert "refresh" not in response.data


# --- Refresh -------------------------------------------------------------


@pytest.mark.django_db
def test_refresh_uses_cookie_and_no_body(user_a) -> None:
    client = _csrf_client()
    _login(client)
    csrf = _csrf(client)

    response = client.post(REFRESH_URL, {}, format="json", HTTP_X_CSRFTOKEN=csrf)

    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert isinstance(response.data["access"], str)


@pytest.mark.django_db
def test_refresh_without_refresh_cookie_returns_401(user_a) -> None:
    client = _csrf_client()
    _login(client)
    csrf = _csrf(client)
    del client.cookies[settings.REFRESH_COOKIE_NAME]

    response = client.post(REFRESH_URL, {}, format="json", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_refresh_with_invalid_refresh_cookie_returns_401(user_a) -> None:
    client = _csrf_client()
    _login(client)
    csrf = _csrf(client)
    client.cookies[settings.REFRESH_COOKIE_NAME] = "not-a-real-token"

    response = client.post(REFRESH_URL, {}, format="json", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_refresh_ignores_refresh_token_in_body(user_a) -> None:
    """A body `refresh` is never honoured — only the cookie is trusted."""
    client = _csrf_client()
    _login(client)
    csrf = _csrf(client)

    response = client.post(
        REFRESH_URL,
        {"refresh": "not-a-real-token"},
        format="json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data


@pytest.mark.django_db
def test_refresh_without_csrf_token_returns_403(user_a) -> None:
    client = _csrf_client()
    _login(client)
    response = client.post(REFRESH_URL, {}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


# --- Logout --------------------------------------------------------------


@pytest.mark.django_db
def test_logout_clears_refresh_cookie(user_a) -> None:
    client = _csrf_client()
    _login(client)
    csrf = _csrf(client)

    response = client.post(LOGOUT_URL, {}, format="json", HTTP_X_CSRFTOKEN=csrf)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    cleared = response.cookies.get(settings.REFRESH_COOKIE_NAME)
    assert cleared is not None
    assert cleared.value == ""
    assert "max-age=0" in cleared.output().lower()


@pytest.mark.django_db
def test_logout_without_csrf_token_returns_403(user_a) -> None:
    client = _csrf_client()
    _login(client)
    assert (
        client.post(LOGOUT_URL, {}, format="json").status_code
        == status.HTTP_403_FORBIDDEN
    )


@pytest.mark.django_db
def test_refresh_after_logout_returns_401(user_a) -> None:
    client = _csrf_client()
    _login(client)
    csrf = _csrf(client)
    client.post(LOGOUT_URL, {}, format="json", HTTP_X_CSRFTOKEN=csrf)

    response = client.post(REFRESH_URL, {}, format="json", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- Current user / protected routes ------------------------------------


@pytest.mark.django_db
def test_current_user_requires_authentication(api_client: APIClient) -> None:
    assert api_client.get(ME_URL).status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_current_user_returns_profile(client_a, user_a) -> None:
    response = client_a.get(ME_URL)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["email"] == user_a.email
    assert response.data["id"] == str(user_a.pk)
    assert "password" not in response.data


# --- Session restoration / reload ----------------------------------------


@pytest.mark.django_db
def test_session_restoration_after_reload(user_a) -> None:
    """Login → (reload) refresh from cookie → call /me with the new access token."""
    client = _csrf_client()
    _login(client)
    csrf = _csrf(client)

    refreshed = client.post(REFRESH_URL, {}, format="json", HTTP_X_CSRFTOKEN=csrf)
    access = refreshed.data["access"]

    response = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {access}")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["email"] == user_a.email


# --- CORS ----------------------------------------------------------------


@pytest.mark.django_db
def test_cors_preflight_reflects_origin_with_credentials(api_client: APIClient) -> None:
    response = api_client.options(
        LOGIN_URL,
        HTTP_ORIGIN="http://localhost:3000",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,x-csrftoken",
    )

    assert response.status_code == status.HTTP_200_OK
    assert (
        response.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
    )
    assert response.headers.get("Access-Control-Allow-Credentials") == "true"
    headers = response.headers.get("Access-Control-Allow-Headers", "")
    assert "x-csrftoken" in headers.lower()


@pytest.mark.django_db
def test_cors_preflight_rejects_untrusted_origin(api_client: APIClient) -> None:
    response = api_client.options(
        LOGIN_URL,
        HTTP_ORIGIN="http://evil.example",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
    )
    assert response.headers.get("Access-Control-Allow-Origin") != "http://evil.example"
