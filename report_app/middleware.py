from django.shortcuts import redirect
from django.urls import reverse


class ApprovedUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and not user.is_superuser:
            profile = getattr(user, "profile", None)
            if profile and not profile.is_approved:
                path = request.path
                allowed_prefixes = (
                    reverse("registration_pending"),
                    reverse("logout"),
                    "/admin/",
                    "/static/",
                    "/media/",
                )
                if not any(path.startswith(prefix) for prefix in allowed_prefixes):
                    return redirect("registration_pending")
        return self.get_response(request)
