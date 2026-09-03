from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from platform_api.apps.institutions.models import Institution, InstitutionType
from platform_api.apps.memberships.models import Membership, MembershipRole, MembershipStatus

User = get_user_model()


@pytest.mark.django_db
class TestPersonaIsolation:
    """Validate dual persona boundary isolation between institutional console and user chat."""

    def test_non_institutional_user_blocked_from_console(self) -> None:
        """A user with no institutional profile cannot log into the institutional console."""
        client = APIClient()
        user = User.objects.create_user(
            email="learner@example.com",
            password="LearnerPassword123!",
            is_email_verified=True,
        )

        response = client.post(
            "/api/v1/auth/login/",
            {"email": "learner@example.com", "password": "LearnerPassword123!"},
            HTTP_X_CLIENT_TYPE="institutional_console",
            format="json",
        )
        assert response.status_code == 400
        assert "This account does not have an institutional profile" in str(response.data)

    def test_institutional_admin_allowed_in_console(self) -> None:
        """A user with active institutional admin membership can log into the console."""
        client = APIClient()
        admin = User.objects.create_user(
            email="headmaster@school.edu",
            password="AdminPassword123!",
            is_email_verified=True,
        )
        institution = Institution.objects.create(
            name="Hill School",
            slug="hill-school",
            institution_type=InstitutionType.SCHOOL,
        )
        Membership.objects.create(
            user=admin,
            institution=institution,
            role=MembershipRole.ADMINISTRATOR,
            status=MembershipStatus.ACTIVE,
        )

        response = client.post(
            "/api/v1/auth/login/",
            {"email": "headmaster@school.edu", "password": "AdminPassword123!"},
            HTTP_X_CLIENT_TYPE="institutional_console",
            format="json",
        )
        assert response.status_code == 200
        assert "access" in response.data

    def test_institutional_admin_blocked_from_user_chat(self) -> None:
        """An institutional administrator cannot access the user chat interface."""
        client = APIClient()
        admin = User.objects.create_user(
            email="principal@college.edu",
            password="AdminPassword123!",
            is_email_verified=True,
        )
        institution = Institution.objects.create(
            name="City College",
            slug="city-college",
            institution_type=InstitutionType.UNIVERSITY,
        )
        Membership.objects.create(
            user=admin,
            institution=institution,
            role=MembershipRole.ADMINISTRATOR,
            status=MembershipStatus.ACTIVE,
        )

        response = client.post(
            "/api/v1/auth/login/",
            {"email": "principal@college.edu", "password": "AdminPassword123!"},
            HTTP_X_CLIENT_TYPE="user_chat",
            format="json",
        )
        assert response.status_code == 400
        assert "Institutional administrator accounts cannot access the student/learner chat interface" in str(response.data)

    def test_learner_allowed_in_user_chat(self) -> None:
        """A standard user without institutional admin rights can access user chat."""
        client = APIClient()
        learner = User.objects.create_user(
            email="student@personal.com",
            password="StudentPassword123!",
            is_email_verified=True,
        )

        response = client.post(
            "/api/v1/auth/login/",
            {"email": "student@personal.com", "password": "StudentPassword123!"},
            HTTP_X_CLIENT_TYPE="user_chat",
            format="json",
        )
        assert response.status_code == 200
        assert "access" in response.data

    def test_superuser_allowed_in_both(self) -> None:
        """Platform superusers and staff maintain operational access across both interfaces."""
        client = APIClient()
        superuser = User.objects.create_superuser(
            email="super@mwalimu.ai",
            password="SuperPassword123!",
        )

        resp_console = client.post(
            "/api/v1/auth/login/",
            {"email": "super@mwalimu.ai", "password": "SuperPassword123!"},
            HTTP_X_CLIENT_TYPE="institutional_console",
            format="json",
        )
        assert resp_console.status_code == 200

        resp_chat = client.post(
            "/api/v1/auth/login/",
            {"email": "super@mwalimu.ai", "password": "SuperPassword123!"},
            HTTP_X_CLIENT_TYPE="user_chat",
            format="json",
        )
        assert resp_chat.status_code == 200
