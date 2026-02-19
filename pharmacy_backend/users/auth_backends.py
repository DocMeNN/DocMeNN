"""
PATH: users/auth_backends.py

AUTH BACKEND: Email OR Username login (not both)

Rules:
- Login accepts EITHER:
  - email (identifier contains "@"), OR
  - username (identifier without "@")
- If request supplies both email + username -> authentication fails (returns None).
  API layer should return 400, but backend enforcement blocks silently for safety.

This is used by Django auth() and DRF flows that call authenticate().
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

User = get_user_model()


class EmailOrUsernameBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Django convention passes "username" as the identifier.
        DRF serializers may pass email=... or username=...

        Enforcement:
        - If both username and email are supplied explicitly -> reject.
        - Otherwise use the one identifier provided.
        """
        # Explicit fields
        email_kw = (kwargs.get("email") or "").strip()
        username_kw = (kwargs.get("username") or "").strip()

        # If caller passed both explicitly, reject (your rule: not both)
        if email_kw and username_kw:
            return None

        identifier = (username or email_kw or username_kw or "").strip()
        if not identifier or password is None:
            return None

        # Decide lookup route
        is_email = "@" in identifier

        try:
            if is_email:
                user = User.objects.get(email__iexact=identifier)
            else:
                user = User.objects.get(username__iexact=identifier)
        except User.DoesNotExist:
            return None

        if not user.is_active:
            return None

        if user.check_password(password):
            return user

        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
