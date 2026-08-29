"""Django command to create or update a Mwalimu Superuser account."""

from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser

User = get_user_model()


class Command(BaseCommand):
    help = "Create or update a superuser account."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--email",
            type=str,
            default="admin@mwalimu.ai",
            help="Superuser email address",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="MwalimuAdmin2026!",
            help="Superuser password",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        email = str(options["email"]).strip().lower()
        password = str(options["password"])

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
                "is_email_verified": True,
            },
        )

        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.is_email_verified = True
        user.set_password(password)
        user.save()

        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully {action} Superuser Account:\n"
                f"  Email:    {email}\n"
                f"  Password: {password}\n"
                f"  Is Staff: {user.is_staff}\n"
                f"  Is Super: {user.is_superuser}"
            )
        )
