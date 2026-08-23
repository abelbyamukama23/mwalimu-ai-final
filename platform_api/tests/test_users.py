"""Tests for the custom User model."""

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from platform_api.apps.users.models import UserManager


@pytest.mark.django_db
def test_user_creation() -> None:
    """A user can be created with an email and password."""
    user_model = get_user_model()
    user = user_model.objects.create_user(
        email="test@example.com", password="secret123"
    )

    assert user.email == "test@example.com"
    assert user.check_password("secret123")
    assert user.is_active is True
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.pk is not None


@pytest.mark.django_db
def test_email_is_unique() -> None:
    """Duplicate emails are rejected at the database level."""
    user_model = get_user_model()
    user_model.objects.create_user(email="dupe@example.com", password="secret123")

    with pytest.raises(IntegrityError):
        user_model.objects.create_user(
            email="dupe@example.com", password="other-secret"
        )


@pytest.mark.django_db
def test_email_is_normalized() -> None:
    """Email addresses are stored in lowercase."""
    user_model = get_user_model()
    user = user_model.objects.create_user(
        email="Mixed.Case@Example.COM", password="secret123"
    )

    assert user.email == "mixed.case@example.com"


@pytest.mark.django_db
def test_password_is_hashed() -> None:
    """Stored password is hashed, not plaintext."""
    user_model = get_user_model()
    user = user_model.objects.create_user(
        email="hash@example.com", password="secret123"
    )

    assert user.password != "secret123"
    assert user.password.startswith("pbkdf2_sha256$")


@pytest.mark.django_db
def test_superuser_creation() -> None:
    """A superuser has staff and superuser flags set."""
    user_model = get_user_model()
    admin = user_model.objects.create_superuser(
        email="admin@example.com", password="admin123"
    )

    assert admin.is_staff is True
    assert admin.is_superuser is True
    assert admin.is_active is True


def test_manager_requires_email() -> None:
    """Creating a user without an email raises ValueError."""
    with pytest.raises(ValueError, match="Users must have an email address"):
        UserManager().create_user(email="", password="secret123")
