# accounting/tests/test_journal_integrity.py

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from django.apps import apps
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounting.models.journal import JournalEntry
from accounting.models.ledger import LedgerEntry
from accounting.services.exceptions import JournalEntryCreationError
from accounting.services.journal_entry_service import create_journal_entry


def _pick_choice_value(field):
    choices = getattr(field, "choices", None)
    if not choices:
        return None

    first = choices[0]
    # flat [(value,label), ...]
    if (
        isinstance(first, (list, tuple))
        and len(first) == 2
        and not isinstance(first[1], (list, tuple))
    ):
        return first[0]
    # grouped [(group, [(value,label), ...]), ...]
    if (
        isinstance(first, (list, tuple))
        and len(first) == 2
        and isinstance(first[1], (list, tuple))
    ):
        inner = first[1]
        if inner and isinstance(inner[0], (list, tuple)) and len(inner[0]) == 2:
            return inner[0][0]
    return None


def _default_for_field(field):
    from django.db import models

    choice_val = _pick_choice_value(field)
    if choice_val is not None:
        return choice_val

    if isinstance(field, models.BooleanField):
        return True
    if isinstance(
        field, (models.IntegerField, models.BigIntegerField, models.SmallIntegerField)
    ):
        return 1
    if isinstance(field, models.DecimalField):
        return Decimal("0.00")
    if isinstance(field, models.DateField) and not isinstance(
        field, models.DateTimeField
    ):
        return date.today()
    if isinstance(field, models.DateTimeField):
        return timezone.now()
    if isinstance(field, models.CharField):
        max_len = getattr(field, "max_length", 255) or 255
        return ("TEST" * 50)[:max_len]
    if isinstance(field, models.TextField):
        return "TEST"
    return None


def _create_active_chart():
    """
    Create a valid active ChartOfAccounts even if the model has extra validation requirements.
    """
    from accounting.models.chart import ChartOfAccounts

    active = ChartOfAccounts.objects.filter(is_active=True).first()
    if active:
        return active

    fields = {f.name: f for f in ChartOfAccounts._meta.fields}
    payload = {"is_active": True}

    if "code" in fields:
        payload["code"] = f"TEST-COA-{uuid.uuid4().hex[:6].upper()}"
    if "name" in fields:
        payload["name"] = "Test Chart of Accounts"

    # fill required non-null, non-default fields
    for fname, field in fields.items():
        if fname in payload:
            continue
        if getattr(field, "primary_key", False) or getattr(
            field, "auto_created", False
        ):
            continue
        if hasattr(field, "has_default") and field.has_default():
            continue
        if getattr(field, "null", False):
            continue
        if field.is_relation and getattr(field, "many_to_one", False):
            continue

        val = _default_for_field(field)
        if val is not None:
            payload[fname] = val

    for _ in range(6):
        try:
            obj = ChartOfAccounts.objects.create(**payload)
            ChartOfAccounts.objects.exclude(id=obj.id).update(is_active=False)
            return obj
        except ValidationError as exc:
            msg = getattr(exc, "message_dict", {}) or {}
            if not msg:
                raise
            for fn in msg.keys():
                if fn in payload:
                    continue
                field = fields.get(fn)
                if field is None:
                    raise
                val = _default_for_field(field)
                if val is not None:
                    payload[fn] = val
                else:
                    raise

    raise ValidationError("Unable to create a valid active ChartOfAccounts for tests.")


def _find_account_model(ChartOfAccounts):
    """
    Locate the Account model: has 'code' field + FK to ChartOfAccounts
    """
    candidates = []
    for m in apps.get_models():
        field_names = {f.name for f in m._meta.fields}
        if "code" not in field_names:
            continue
        for f in m._meta.fields:
            if (
                f.is_relation
                and getattr(f, "many_to_one", False)
                and getattr(f.remote_field, "model", None) == ChartOfAccounts
            ):
                candidates.append((m, f.name))
                break
    return candidates[0] if candidates else (None, None)


def _ensure_account(chart, code: str, name: str):
    ChartOfAccounts = chart.__class__
    AccountModel, chart_fk = _find_account_model(ChartOfAccounts)
    if AccountModel is None:
        raise RuntimeError(
            "Could not locate Account model (code + FK to ChartOfAccounts)."
        )

    fields = {f.name: f for f in AccountModel._meta.fields}

    qs = AccountModel.objects.filter(code=str(code)).filter(**{chart_fk: chart})
    obj = qs.first()
    if obj:
        if "is_active" in fields and getattr(obj, "is_active", True) is not True:
            setattr(obj, "is_active", True)
            obj.save(update_fields=["is_active"])
        return obj

    payload = {chart_fk: chart, "code": str(code)}
    if "name" in fields:
        payload["name"] = name
    if "is_active" in fields:
        payload["is_active"] = True

    for fname, field in fields.items():
        if fname in payload:
            continue
        if getattr(field, "primary_key", False) or getattr(
            field, "auto_created", False
        ):
            continue
        if hasattr(field, "has_default") and field.has_default():
            continue
        if getattr(field, "null", False):
            continue
        if field.is_relation and getattr(field, "many_to_one", False):
            continue

        val = _default_for_field(field)
        if val is not None:
            payload[fname] = val

    return AccountModel.objects.create(**payload)


class JournalEntryServiceTests(TestCase):
    def setUp(self):
        self.chart = _create_active_chart()

        # minimal accounts used in our test postings
        self.cash = _ensure_account(self.chart, "1000", "Cash")
        self.sales = _ensure_account(self.chart, "4000", "Sales Revenue")

    def test_create_journal_entry_balanced_creates_ledger(self):
        je = create_journal_entry(
            description="Test sale",
            postings=[
                {"account": self.cash, "debit": "100.00", "credit": "0.00"},
                {"account": self.sales, "debit": "0.00", "credit": "100.00"},
            ],
            reference_type="TEST",
            reference_id="A1",
        )

        self.assertIsInstance(je, JournalEntry)
        self.assertTrue(JournalEntry.objects.filter(id=je.id).exists())

        lines = LedgerEntry.objects.filter(journal_entry=je)
        self.assertEqual(lines.count(), 2)

        debit_sum = sum(
            (l.amount for l in lines if l.entry_type == LedgerEntry.DEBIT),
            Decimal("0.00"),
        )
        credit_sum = sum(
            (l.amount for l in lines if l.entry_type == LedgerEntry.CREDIT),
            Decimal("0.00"),
        )
        self.assertEqual(debit_sum, Decimal("100.00"))
        self.assertEqual(credit_sum, Decimal("100.00"))

    def test_unbalanced_raises(self):
        with self.assertRaises(JournalEntryCreationError):
            create_journal_entry(
                description="Bad entry",
                postings=[
                    {"account": self.cash, "debit": "100.00", "credit": "0.00"},
                    {"account": self.sales, "debit": "0.00", "credit": "90.00"},
                ],
                reference_type="TEST",
                reference_id="BAD1",
            )
