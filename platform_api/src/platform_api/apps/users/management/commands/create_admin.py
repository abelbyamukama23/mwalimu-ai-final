"""Django command to create or update a Mwalimu Superuser account."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Create or update a superuser account."

    def add_arguments(self, parser):
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

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        password = options["password"]

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )

        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
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
