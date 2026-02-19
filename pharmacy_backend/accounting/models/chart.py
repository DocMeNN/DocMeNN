# accounting/models/chart.py

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models, transaction


class ChartOfAccounts(models.Model):
    """
    Represents a Chart of Accounts for a business type.

    Enterprise rules:
    - Only ONE chart can be active at a time.
    - Business type is explicit (pharmacy / supermarket / retail).
    - A stable key exists so code doesn't depend on chart.name formatting.

    MIGRATION-SAFE NOTE:
    - code and business_type are temporarily nullable to allow smooth migration
      of existing rows without forcing a single default.
    - Seed commands will backfill these for existing charts.
    - After backfill, we can make them non-null in a follow-up migration.
    """

    BUSINESS_PHARMACY = "pharmacy"
    BUSINESS_SUPERMARKET = "supermarket"
    BUSINESS_RETAIL = "retail"

    BUSINESS_TYPE_CHOICES = [
        (BUSINESS_PHARMACY, "Pharmacy"),
        (BUSINESS_SUPERMARKET, "Supermarket"),
        (BUSINESS_RETAIL, "General Retail"),
    ]

    # Human label (fine to change in admin)
    name = models.CharField(max_length=100, unique=True)

    # Stable key for code mapping (recommended). Example: "supermarket_standard"
    # TEMP nullable for migration safety; will be enforced after backfill.
    code = models.SlugField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        default=None,
        help_text="Stable chart key used by resolvers/seeders. Do not change after go-live.",
    )

    # Explicit business type (prevents name-based ambiguity)
    # TEMP nullable for migration safety; will be enforced after backfill.
    business_type = models.CharField(
        max_length=32,
        choices=BUSINESS_TYPE_CHOICES,
        null=True,
        blank=True,
        default=None,
        db_index=True,
    )

    # Optional industry label (keep what you had)
    industry = models.CharField(max_length=100, blank=True, default="")

    # IMPORTANT: default False is safer; seeding can activate explicitly.
    is_active = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Chart of Accounts"
        verbose_name_plural = "Charts of Accounts"
        ordering = ["name"]

    def __str__(self):
        bt = getattr(self, "business_type", "") or "unknown"
        return f"{self.name} ({bt})"

    def clean(self):
        # Allow nulls ONLY for legacy migration state.
        # For new records (or edited ones), require values.
        if self._state.adding:
            if not (self.code or "").strip():
                raise ValidationError({"code": "code is required"})
            if not (self.business_type or "").strip():
                raise ValidationError({"business_type": "business_type is required"})

    def save(self, *args, **kwargs):
        """
        Enforce that only ONE Chart of Accounts can be active at a time,
        and clear resolver cache when switching actives.
        """
        self.full_clean()

        from accounting.services.account_resolver import clear_active_chart_cache

        with transaction.atomic():
            was_active = False
            if self.pk:
                prev = (
                    ChartOfAccounts.objects.filter(pk=self.pk)
                    .values_list("is_active", flat=True)
                    .first()
                )
                was_active = bool(prev)

            if self.is_active:
                ChartOfAccounts.objects.exclude(pk=self.pk).update(is_active=False)

            super().save(*args, **kwargs)

        # If active chart status changed, clear resolver cache
        if self.is_active or was_active:
            clear_active_chart_cache()
