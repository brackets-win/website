"""Auto-sign-in for local DEBUG runs only (never enabled in production)."""

from __future__ import annotations

import os

from django.conf import settings
from django.contrib.auth import login


class DevAutoLoginMiddleware:
    """
    When DEBUG is on, log in a local test user so the SPA can load without credentials.
  Set DEV_AUTO_LOGIN_USER to override the username (default: demo).
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._username = os.environ.get("DEV_AUTO_LOGIN_USER", "demo")

    def __call__(self, request):
        if settings.DEBUG and not request.user.is_authenticated:
            from brackets.models import User

            user, created = User.objects.get_or_create(
                username=self._username,
                defaults={
                    "email": f"{self._username}@localhost",
                    "is_staff": True,
                },
            )
            if created:
                user.set_password("demo")
                user.is_staff = True
                user.save()
            login(request, user)
        return self.get_response(request)
