# store/models/store.py

import uuid

from django.db import models
from django.db.models import Q


class Store(models.Model):
    """
    Represents a physical store / branch.

    Phase 2 guarantees:
    - Stores are stable master-data
    - code is optional, but if provided it must be unique
    - timestamps are reliable (not nullable)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=255)

    # Optional, but if provided must be unique
    code = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Unique store/branch code (optional). If set, must be unique.",
        db_index=True,
    )

    address = models.TextField(blank=True)
    phone = models.CharField(max_length=50, blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=Q(code__isnull=False) & ~Q(code=""),
                name="uniq_store_code_when_present",
            ),
        ]

    def __str__(self):
        c = (self.code or "").strip()
        if c:
            return f"{self.name} ({c})"
        return self.name
