"""
PATH: users/models/user.py

CUSTOM USER MODEL

HotSprint Auth Upgrade:
- Registration can accept BOTH username + email (recommended).
- Registration can also accept ONLY username (email auto-generated) OR ONLY email (username auto-generated).
- Login should allow EITHER username OR email (not both) — enforced by custom auth backend.

Migration safety:
- username is kept NULLABLE for now because existing DB rows already contain NULL usernames.
- New users will always get a username set by the UserManager.
- Later, after backfilling existing rows, we can migrate username to non-null safely.
"""

from __future__ import annotations

import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.core.exceptions import ValidationError


# ---------------- USER MANAGER ----------------
class UserManager(BaseUserManager):
    def create_user(self, email=None, password=None, **extra_fields):
        """
        Backward-compatible creation supporting:
        - create_user(email="a@b.com", password="x", username="john")
        - create_user(username="cashier", password="x")   ✅ tests
        - create_user(email="a@b.com", password="x")

        Rules:
        - Must provide at least one of: email or username.
        - If email missing but username present: email becomes <username>@local.test
        - If username missing but email present: username becomes email local-part (uniqueness ensured)
        """
        username = (extra_fields.get("username") or "").strip()
        email = (email or extra_fields.get("email") or "").strip()

        if not email and not username:
            raise ValueError("Provide at least email or username")

        if not email and username:
            email = f"{username.lower()}@local.test"

        email = self.normalize_email(email)

        if email and not username:
            base = (email.split("@")[0] or "user").strip().lower()
            candidate = base
            i = 1
            while self.model.objects.filter(username__iexact=candidate).exists():
                i += 1
                candidate = f"{base}{i}"
            username = candidate

        extra_fields["email"] = email
        extra_fields["username"] = username or None  # migration-safe
        extra_fields.setdefault("is_active", True)

        user = self.model(**extra_fields)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.full_clean()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Superuser must have an email")
        if not password:
            raise ValueError("Superuser must have a password")

        extra_fields.setdefault("role", "admin")
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")

        # Ensure username exists (derive if not provided)
        if not (extra_fields.get("username") or "").strip():
            base = (self.normalize_email(email).split("@")[0] or "admin").strip().lower()
            candidate = base
            i = 1
            while self.model.objects.filter(username__iexact=candidate).exists():
                i += 1
                candidate = f"{base}{i}"
            extra_fields["username"] = candidate

        return self.create_user(email=email, password=password, **extra_fields)


# ---------------- USER MODEL ----------------
class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("manager", "Manager"),
        ("pharmacist", "Pharmacist"),
        ("cashier", "Cashier"),
        ("reception", "Reception"),
        ("customer", "Customer"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ✅ Keep nullable for migration safety (existing rows may be NULL)
    username = models.CharField(max_length=150, unique=True, null=True, blank=True)

    # Canonical identity
    email = models.EmailField(unique=True)

    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="customer")

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # keep createsuperuser simple; username is auto-derived if missing

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.email:
            self.email = self.__class__.objects.normalize_email(self.email).strip()
        if self.username is not None:
            self.username = self.username.strip() or None

        if not self.email and not self.username:
            raise ValidationError("User must have at least email or username")

    def __str__(self):
        ident = self.username or self.email
        return f"{ident} ({self.role})"
