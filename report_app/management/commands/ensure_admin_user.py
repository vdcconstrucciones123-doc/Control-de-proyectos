import os

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Create or update an admin user from environment variables if they are defined."

    def handle(self, *args, **options):
        username = (
            os.getenv("DJANGO_SUPERUSER_USERNAME")
            or os.getenv("ADMIN_USERNAME")
            or os.getenv("SUPERUSER_USERNAME")
            or ""
        ).strip()
        password = (
            os.getenv("DJANGO_SUPERUSER_PASSWORD")
            or os.getenv("ADMIN_PASSWORD")
            or os.getenv("SUPERUSER_PASSWORD")
            or ""
        ).strip()
        email = (
            os.getenv("DJANGO_SUPERUSER_EMAIL")
            or os.getenv("ADMIN_EMAIL")
            or os.getenv("SUPERUSER_EMAIL")
            or ""
        ).strip()
        allow_default_admin = os.getenv("ALLOW_DEFAULT_ADMIN", "").strip().lower() in {"1", "true", "yes"}

        if not username and not password and (settings.DEBUG or allow_default_admin):
            username = "ADMIN"
            password = "ADMIN"
            email = email or "admin@example.com"

        if not username or not password:
            self.stdout.write(
                self.style.WARNING(
                    "Admin bootstrap skipped. Set DJANGO_SUPERUSER_USERNAME and DJANGO_SUPERUSER_PASSWORD in Render."
                )
            )
            return

        User = get_user_model()
        UserProfile = None
        try:
            from report_app.models import UserProfile
        except Exception:
            UserProfile = None

        defaults = {
            "email": email,
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
        }
        user, created = User.objects.get_or_create(username=username, defaults=defaults)

        changed = False
        if email and user.email != email:
            user.email = email
            changed = True
        if not user.is_staff:
            user.is_staff = True
            changed = True
        if not user.is_superuser:
            user.is_superuser = True
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True

        if not user.check_password(password):
            user.set_password(password)
            changed = True

        if created or changed:
            user.save()

        if UserProfile is not None:
            profile, profile_created = UserProfile.objects.get_or_create(user=user)
            if not profile.is_approved:
                profile.is_approved = True
                profile.approved_at = timezone.now()
                profile.save(update_fields=["is_approved", "approved_at"])
                profile_created = True

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} admin user '{username}'. Access /admin/ with these credentials."))
