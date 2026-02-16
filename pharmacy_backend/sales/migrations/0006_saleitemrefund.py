"""
======================================================
PATH: sales/migrations/0006_saleitemrefund.py
======================================================
MIGRATION: CREATE SaleItemRefund (PARTIAL REFUNDS)

Purpose:
- Adds append-only SaleItemRefund table to support partial refunds.
- Fixes runtime error: "no such table: sales_saleitemrefund"
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0005_alter_sale_payment_method_salepaymentallocation"),
    ]

    operations = [
        migrations.CreateModel(
            name="SaleItemRefund",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True,
                        default=uuid.uuid4,
                        editable=False,
                        serialize=False,
                    ),
                ),
                (
                    "quantity_refunded",
                    models.PositiveIntegerField(
                        help_text="Quantity refunded for this sale item (immutable)."
                    ),
                ),
                (
                    "unit_price_snapshot",
                    models.DecimalField(
                        max_digits=12,
                        decimal_places=2,
                        help_text="Unit selling price at time of refund (snapshot).",
                    ),
                ),
                (
                    "unit_cost_snapshot",
                    models.DecimalField(
                        max_digits=12,
                        decimal_places=2,
                        help_text="Unit cost at time of refund (snapshot).",
                    ),
                ),
                (
                    "reason",
                    models.TextField(
                        null=True,
                        blank=True,
                        help_text="Optional refund reason.",
                    ),
                ),
                (
                    "refunded_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                (
                    "refunded_by",
                    models.ForeignKey(
                        to=settings.AUTH_USER_MODEL,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sale_item_refunds",
                    ),
                ),
                (
                    "sale",
                    models.ForeignKey(
                        to="sales.sale",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="item_refunds",
                    ),
                ),
                (
                    "sale_item",
                    models.ForeignKey(
                        to="sales.saleitem",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="refunds",
                    ),
                ),
            ],
            options={
                "ordering": ["refunded_at"],
            },
        ),
        migrations.AddIndex(
            model_name="saleitemrefund",
            index=models.Index(fields=["sale", "refunded_at"], name="sales_saleit_sale_id_9c3a3f_idx"),
        ),
        migrations.AddIndex(
            model_name="saleitemrefund",
            index=models.Index(fields=["sale_item", "refunded_at"], name="sales_saleit_sale_it_5b2e2c_idx"),
        ),
    ]
