"""Tests for UserProfile and UserPreference models, APIs, and authorization."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from platform_api.apps.users.models import (
    ExplanationDepth,
    PedagogicalStyle,
    User,
    UserPreference,
    UserProfile,
)


@pytest.mark.django_db
class TestUserProfile:
    """Test suite for UserProfile model and API."""

    def test_profile_auto_creation_on_get(self) -> None:
        """GET /api/v1/users/profile/ auto-creates profile if not present."""
        user = User.objects.create_user(
            email="learner1@mwalimu.ai",
            password="password123",
        )
        client = APIClient()
        client.force_authenticate(user=user)

        assert not UserProfile.objects.filter(user=user).exists()

        response = client.get(reverse("user_profile"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["display_name"] == ""
        assert response.data["bio"] == ""

        # Verified created in DB
        profile = UserProfile.objects.get(user=user)
        assert profile.display_name == ""

    def test_profile_patch_update(self) -> None:
        """PATCH /api/v1/users/profile/ updates display_name, avatar_url, bio."""
        user = User.objects.create_user(
            email="teacher1@mwalimu.ai",
            password="password123",
        )
        client = APIClient()
        client.force_authenticate(user=user)

        payload = {
            "display_name": "Mwalimu Kenneth",
            "bio": "High school biology teacher in Nairobi.",
            "phone_number": "+254700000000",
        }
        response = client.patch(reverse("user_profile"), payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["display_name"] == "Mwalimu Kenneth"
        assert response.data["bio"] == "High school biology teacher in Nairobi."
        assert response.data["phone_number"] == "+254700000000"

        # Verify DB persistence
        profile = UserProfile.objects.get(user=user)
        assert profile.display_name == "Mwalimu Kenneth"

    def test_unauthenticated_profile_access_denied(self) -> None:
        """Unauthenticated requests return 401."""
        client = APIClient()
        response = client.get(reverse("user_profile"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestUserPreference:
    """Test suite for UserPreference model and API."""

    def test_preferences_auto_creation_on_get(self) -> None:
        """GET /api/v1/users/preferences/ returns default preferences."""
        user = User.objects.create_user(
            email="learner2@mwalimu.ai",
            password="password123",
        )
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get(reverse("user_preferences"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["pedagogical_style"] == PedagogicalStyle.INTUITIVE
        assert response.data["explanation_depth"] == ExplanationDepth.STANDARD
        assert response.data["response_language"] == "en"
        assert response.data["cross_session_memory"] is True

    def test_preferences_patch_update(self) -> None:
        """PATCH /api/v1/users/preferences/ updates pedagogical style and depth."""
        user = User.objects.create_user(
            email="learner3@mwalimu.ai",
            password="password123",
        )
        client = APIClient()
        client.force_authenticate(user=user)

        payload = {
            "pedagogical_style": PedagogicalStyle.SOCRATIC,
            "explanation_depth": ExplanationDepth.IN_DEPTH,
            "response_language": "sw",
            "cross_session_memory": False,
        }
        response = client.patch(reverse("user_preferences"), payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["pedagogical_style"] == PedagogicalStyle.SOCRATIC
        assert response.data["explanation_depth"] == ExplanationDepth.IN_DEPTH
        assert response.data["response_language"] == "sw"
        assert response.data["cross_session_memory"] is False

        # Verify DB persistence
        pref = UserPreference.objects.get(user=user)
        assert pref.pedagogical_style == PedagogicalStyle.SOCRATIC
        assert pref.response_language == "sw"

    def test_invalid_pedagogical_style_rejected(self) -> None:
        """Invalid choice returns 400."""
        user = User.objects.create_user(
            email="learner4@mwalimu.ai",
            password="password123",
        )
        client = APIClient()
        client.force_authenticate(user=user)

        payload = {"pedagogical_style": "invalid_style"}
        response = client.patch(reverse("user_preferences"), payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_current_user_me_endpoint_includes_profile(self) -> None:
        """GET /api/v1/auth/me/ includes nested profile."""
        user = User.objects.create_user(
            email="profile_test@mwalimu.ai",
            password="password123",
        )
        UserProfile.objects.create(user=user, display_name="Jane Doe")
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get(reverse("current_user"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["profile"]["display_name"] == "Jane Doe"
