"""User model and manager for the Mwalimu Platform API."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):  # type: ignore[type-arg]
    """Custom user manager using email as the unique identifier."""

    def _normalize_email(self, email: str | None) -> str:
        """Normalize an email address by lowercasing the domain part."""
        if not email:
            return ""
        email = email.strip().lower()
        return email

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: object,
    ) -> User:
        """Create and save a regular user with the given email and password."""
        if not email:
            raise ValueError("Users must have an email address.")
        email = self._normalize_email(email)
        extra_fields.setdefault("is_active", True)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user  # type: ignore[no-any-return]

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: object,
    ) -> User:
        """Create and save a superuser with the given email and password."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superusers must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superusers must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model using email as the unique login identifier."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD: ClassVar[str] = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        """Model metadata."""

        db_table = "users_user"
        ordering = ["-created_at"]
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self) -> str:
        """Return the user's email address."""
        return self.email

    def clean(self) -> None:
        """Normalize the email address before validation."""
        super().clean()
        self.email = self.email.strip().lower() if self.email else ""


class UserProfile(models.Model):
    """User profile metadata separate from the core authentication identity."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    display_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="User's public/chosen display name.",
    )
    avatar_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="URL pointing to the user's avatar image.",
    )
    phone_number = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Optional contact phone number.",
    )
    bio = models.TextField(
        blank=True,
        default="",
        help_text="Short biographical summary or teaching/learning focus.",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "users_profile"
        ordering = ["-created_at"]
        verbose_name = "user profile"
        verbose_name_plural = "user profiles"

    def __str__(self) -> str:
        """Return display name or user email."""
        return self.display_name or str(self.user)


class PedagogicalStyle(models.TextChoices):
    """Pedagogical explanation style."""

    INTUITIVE = "intuitive", "Intuitive & Analogy-driven"
    FORMAL = "formal", "Formal & Academic"
    SOCRATIC = "socratic", "Socratic & Inquiring"


class ExplanationDepth(models.TextChoices):
    """Explanation depth level."""

    CONCISE = "concise", "Concise Summary"
    STANDARD = "standard", "Standard Explanation"
    IN_DEPTH = "in_depth", "In-depth / Deep Dive"


class UserPreference(models.Model):
    """User pedagogical and reasoning preferences for AI interactions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="preferences",
    )
    pedagogical_style = models.CharField(
        max_length=20,
        choices=PedagogicalStyle.choices,
        default=PedagogicalStyle.INTUITIVE,
        help_text="Preferred style for explanations.",
    )
    explanation_depth = models.CharField(
        max_length=20,
        choices=ExplanationDepth.choices,
        default=ExplanationDepth.STANDARD,
        help_text="Preferred depth/detail level for explanations.",
    )
    response_language = models.CharField(
        max_length=10,
        default="en",
        help_text="Target language for AI explanations (e.g., 'en', 'sw').",
    )
    cross_session_memory = models.BooleanField(
        default=True,
        help_text="Allow Mwalimu to reference relevant concepts across chat sessions.",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "users_preference"
        ordering = ["-created_at"]
        verbose_name = "user preference"
        verbose_name_plural = "user preferences"

    def __str__(self) -> str:
        """Return string representation."""
        return f"Preferences for {self.user}"

