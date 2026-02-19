# users/models.py

import uuid

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models


# ---------------- USER MANAGER ----------------
class UserManager(BaseUserManager):
    def create_user(self, email=None, password=None, **extra_fields):
        """
        Backward-compatible user creation.

        Tests in this project still call:
            create_user(username="...", password="...")

        But our canonical auth identity is email.

        Rules:
        - If email is missing but username is provided, generate email as: <username>@local.test
        - Strip out unknown fields like 'username' so model init doesn't crash.
        """
        username = (extra_fields.pop("username", "") or "").strip()

        if not email:
            if username:
                email = f"{username.lower()}@local.test"
            else:
                raise ValueError(
                    "An email address is required (or provide username=...)"
                )

        email = self.normalize_email(email)
        extra_fields.setdefault("is_active", True)

        user = self.model(email=email, **extra_fields)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
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

        return self.create_user(email=email, password=password, **extra_fields)


# ---------------- USER MODEL ----------------
class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("pharmacist", "Pharmacist"),
        ("cashier", "Cashier"),
        ("reception", "Reception"),
        ("customer", "Customer"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)

    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="customer",
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} ({self.role})"
