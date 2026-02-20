# PATH: accounting/services/account_resolver.py

"""
PATH: accounting/services/account_resolver.py

ACCOUNT RESOLVER (AUTHORITATIVE)

This module answers ONE question:
"Which account should be used for this purpose?"

It is chart-aware: different charts may use different codes
for the same semantic account (e.g., Inventory code differs).

Design goals:
- deterministic
- chart-safe
- hard-fail on missing setup (so we don't post to wrong accounts)

HOTSPRINT UPGRADE:
- Adds COGS semantic + get_cogs_account() for cost-side posting.
- Hardened mapping behavior + clearer failure messages.
- More resilient chart-key matching (not brittle on chart.name formatting).

PHASE 5 UPGRADE (Tenant Safety Helpers):
- Keep existing get_active_chart() behavior (single active chart) for backward compatibility.
- Add best-effort chart resolution helpers for multi-business isolation:
    - get_chart_for_business(business_id)
    - user_can_access_business(user, business_id)
  These helpers do NOT assume your schema, but will enforce scoping if ChartOfAccounts
  exposes a business relation (e.g., business_id / business FK).

ADR-001 (Bootstrap CoA):
- If no active chart exists, automatically bootstrap ONE safely (idempotent).
- If multiple active charts exist, hard-fail (do NOT auto-fix silently).
"""

from __future__ import annotations

import logging
from functools import lru_cache

from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.db import transaction

from accounting.models.account import Account
from accounting.models.chart import ChartOfAccounts
from accounting.services.exceptions import AccountResolutionError

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# SEMANTIC CODES BY CHART KEY
# ------------------------------------------------------------

CHART_CODE_MAP = {
    # -------- Pharmacy --------
    "Pharmacy Standard Chart": {
        "CASH": "1000",
        "BANK": "1010",
        "AR": "1200",
        "INVENTORY": "1100",
        "ACCOUNTS_PAYABLE": "2000",
        "VAT_PAYABLE": "2100",
        "SALES_REVENUE": "4000",
        "SALES_DISCOUNT": "4050",
        "COGS": "5000",
    },
    # -------- General Retail --------
    "General Retail": {
        "CASH": "1000",
        "BANK": "1010",
        "AR": "1100",
        "INVENTORY": "1200",
        "ACCOUNTS_PAYABLE": "2000",
        "VAT_PAYABLE": "2100",
        "SALES_REVENUE": "4000",
        "SALES_DISCOUNT": "4050",
        "COGS": "5000",
    },
    # -------- Supermarket --------
    "Supermarket": {
        "CASH": "1000",
        "BANK": "1010",
        "AR": "1100",
        "INVENTORY": "1200",
        "ACCOUNTS_PAYABLE": "2000",
        "VAT_PAYABLE": "2100",
        "SALES_REVENUE": "4000",
        "SALES_DISCOUNT": "4050",
        "COGS": "5000",
    },
}

DEFAULT_CODES = {
    "CASH": "1000",
    "BANK": "1010",
    "AR": "1100",
    "INVENTORY": "1200",
    "ACCOUNTS_PAYABLE": "2000",
    "VAT_PAYABLE": "2100",
    "SALES_REVENUE": "4000",
    "SALES_DISCOUNT": "4050",
    "COGS": "5000",
}

# ADR-001: default name used when we must create a brand-new chart
DEFAULT_BOOTSTRAP_CHART_NAME = "Pharmacy Standard Chart"


def _norm(s: str) -> str:
    if s is None:
        return ""
    return " ".join(str(s).strip().lower().split())


def _chart_match_keys(chart: ChartOfAccounts) -> list[str]:
    keys: list[str] = []

    name = getattr(chart, "name", None)
    if name:
        keys.append(str(name))  # exact
        keys.append(_norm(name))  # normalized

    # Optional identifiers (safe if fields don't exist)
    for attr in ("business_type", "slug", "code"):
        v = getattr(chart, attr, None)
        if v:
            keys.append(_norm(v))

    seen = set()
    out = []
    for k in keys:
        if k and k not in seen:
            out.append(k)
            seen.add(k)
    return out


def _codes_for_chart(chart: ChartOfAccounts) -> dict:
    name = getattr(chart, "name", None)
    if name and name in CHART_CODE_MAP:
        return CHART_CODE_MAP[name]

    normalized_map = {_norm(k): v for k, v in CHART_CODE_MAP.items()}
    for key in _chart_match_keys(chart):
        nk = _norm(key)
        if nk in normalized_map:
            return normalized_map[nk]

    return DEFAULT_CODES


def _has_chart_field(field_name: str) -> bool:
    """
    Safe schema probe. Returns True if ChartOfAccounts has field field_name.
    """
    try:
        ChartOfAccounts._meta.get_field(field_name)
        return True
    except Exception:
        return False


# ------------------------------------------------------------
# ADR-001: BOOTSTRAP HELPERS
# ------------------------------------------------------------


def _ensure_single_active_chart() -> ChartOfAccounts:
    """
    ADR-001 enforcement:
    - If exactly one active chart exists -> return it
    - If none active -> activate an existing chart if present, else create one
    - If multiple active -> hard-fail (do NOT auto-fix silently)

    This runs inside a DB transaction to be concurrency-safe.
    """
    with transaction.atomic():
        # lock the active set for concurrency safety
        active_qs = ChartOfAccounts.objects.select_for_update().filter(is_active=True)
        active_count = active_qs.count()

        if active_count == 1:
            return active_qs.first()

        if active_count > 1:
            raise AccountResolutionError(
                "Multiple active Charts of Accounts found. Only one active chart is allowed."
            )

        # active_count == 0: bootstrap path
        # Prefer activating an existing chart to avoid failing on required fields.
        existing = ChartOfAccounts.objects.select_for_update().order_by("id").first()
        if existing:
            # Ensure no other charts are active (should already be true, but keep it explicit)
            ChartOfAccounts.objects.select_for_update().filter(is_active=True).update(
                is_active=False
            )
            existing.is_active = True
            existing.save(update_fields=["is_active"])

            logger.warning(
                "ADR-001 bootstrap: Activated existing ChartOfAccounts id=%s name=%s",
                getattr(existing, "id", None),
                getattr(existing, "name", None),
            )
            return existing

        # No charts exist at all: create a default one
        chart = ChartOfAccounts.objects.create(
            name=DEFAULT_BOOTSTRAP_CHART_NAME,
            is_active=True,
        )
        logger.warning(
            "ADR-001 bootstrap: Created default ChartOfAccounts id=%s name=%s",
            getattr(chart, "id", None),
            getattr(chart, "name", None),
        )
        return chart


# ------------------------------------------------------------
# ACTIVE CHART (ADR-001 UPGRADED)
# ------------------------------------------------------------


@lru_cache(maxsize=1)
def get_active_chart() -> ChartOfAccounts:
    """
    Cached resolver for the *single* active chart.

    ADR-001 behavior:
    - If exactly one active -> return it
    - If none active -> bootstrap automatically (idempotent)
    - If multiple active -> hard-fail

    NOTE:
    If you toggle active charts in admin or tests, call clear_active_chart_cache().
    """
    try:
        return ChartOfAccounts.objects.get(is_active=True)
    except ObjectDoesNotExist:
        chart = _ensure_single_active_chart()
        clear_active_chart_cache()
        return chart
    except MultipleObjectsReturned as exc:
        raise AccountResolutionError(
            "Multiple active Charts of Accounts found. Only one active chart is allowed."
        ) from exc


def clear_active_chart_cache() -> None:
    get_active_chart.cache_clear()


def get_active_chart_signature() -> str:
    chart = get_active_chart()
    return f"{chart.id}:{getattr(chart, 'name', '')}:{int(bool(getattr(chart, 'is_active', False)))}"


# ------------------------------------------------------------
# PHASE 5: TENANT SAFETY HELPERS (BEST-EFFORT)
# ------------------------------------------------------------


def get_chart_for_business(business_id: int) -> ChartOfAccounts:
    """
    Best-effort: resolve chart by business.

    Supported schemas (if present on ChartOfAccounts):
    - business_id (int field)
    - business (FK) -> uses business_id behind the scenes

    If your schema does NOT include these fields, we hard-fail with a clear message,
    because we cannot safely prevent cross-business posting.

    This is intentionally strict: tenant safety > convenience.
    """
    if business_id is None:
        raise AccountResolutionError("business_id is required")

    qs = ChartOfAccounts.objects.all()

    if _has_chart_field("business_id"):
        qs = qs.filter(business_id=business_id)
    elif _has_chart_field("business"):
        qs = qs.filter(business__id=business_id)
    else:
        raise AccountResolutionError(
            "ChartOfAccounts is not business-scoped (missing business_id/business field). "
            "Add business scoping to ChartOfAccounts to enforce tenant isolation."
        )

    # If you expect multiple charts per business, tighten this to select “active within business”.
    # For now, prefer an active chart if present, else fall back to first.
    active = qs.filter(is_active=True).first()
    if active:
        return active

    chart = qs.first()
    if not chart:
        raise AccountResolutionError(f"No ChartOfAccounts found for business_id={business_id}")
    return chart


def user_can_access_business(user, business_id: int) -> bool:
    """
    Central policy hook for endpoints that accept business_id.

    Current safe rule:
    - Superuser: allowed
    - Otherwise: if charts are business-scoped, user can only act on the active chart's business.

    If you later add a membership model (UserBusiness, etc.), enforce it here.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True

    # If ChartOfAccounts is business-scoped, enforce "active business only"
    chart = get_active_chart()

    if _has_chart_field("business_id"):
        return int(getattr(chart, "business_id", -1) or -1) == int(business_id)
    if _has_chart_field("business"):
        b = getattr(chart, "business", None)
        return bool(b and int(getattr(b, "id", -1)) == int(business_id))

    # If schema is not scoped, we cannot safely assert access. Deny by default.
    return False


# ------------------------------------------------------------
# INTERNAL RESOLUTION HELPERS
# ------------------------------------------------------------


def _resolve_code(*, semantic_key: str, chart: ChartOfAccounts) -> str:
    semantic_key = (semantic_key or "").strip().upper()
    if not semantic_key:
        raise AccountResolutionError("semantic_key is required")

    codes = _codes_for_chart(chart)
    code = (codes.get(semantic_key) or "").strip()

    if not code:
        chart_name = getattr(chart, "name", "ACTIVE_CHART")
        raise AccountResolutionError(
            f"Missing mapping for semantic key '{semantic_key}' in chart '{chart_name}'. "
            "Update CHART_CODE_MAP and ensure your seed command creates the account code."
        )

    return code


def _get_account_by_code(*, chart: ChartOfAccounts, code: str) -> Account:
    code = (code or "").strip()
    if not code:
        raise AccountResolutionError("Account code is required")

    try:
        return Account.objects.get(chart=chart, code=code, is_active=True)
    except ObjectDoesNotExist as exc:
        raise AccountResolutionError(
            f"Account with code={code} not found (or inactive) in active chart '{getattr(chart, 'name', 'ACTIVE_CHART')}'. "
            "Run the chart seed command (or add the account manually) and ensure is_active=True."
        ) from exc
    except MultipleObjectsReturned as exc:
        raise AccountResolutionError(
            f"Multiple active accounts found with code={code} in active chart '{getattr(chart, 'name', 'ACTIVE_CHART')}'."
        ) from exc


# ------------------------------------------------------------
# PUBLIC RESOLVERS
# ------------------------------------------------------------


def get_cash_account() -> Account:
    chart = get_active_chart()
    return _get_account_by_code(
        chart=chart, code=_resolve_code(semantic_key="CASH", chart=chart)
    )


def get_bank_account() -> Account:
    chart = get_active_chart()
    return _get_account_by_code(
        chart=chart, code=_resolve_code(semantic_key="BANK", chart=chart)
    )


def get_accounts_receivable_account() -> Account:
    chart = get_active_chart()
    return _get_account_by_code(
        chart=chart, code=_resolve_code(semantic_key="AR", chart=chart)
    )


def get_inventory_account() -> Account:
    chart = get_active_chart()
    return _get_account_by_code(
        chart=chart, code=_resolve_code(semantic_key="INVENTORY", chart=chart)
    )


def get_cogs_account() -> Account:
    chart = get_active_chart()
    return _get_account_by_code(
        chart=chart, code=_resolve_code(semantic_key="COGS", chart=chart)
    )


def get_accounts_payable_account() -> Account:
    chart = get_active_chart()
    return _get_account_by_code(
        chart=chart, code=_resolve_code(semantic_key="ACCOUNTS_PAYABLE", chart=chart)
    )


def get_sales_revenue_account() -> Account:
    chart = get_active_chart()
    return _get_account_by_code(
        chart=chart, code=_resolve_code(semantic_key="SALES_REVENUE", chart=chart)
    )


def get_sales_discount_account() -> Account:
    chart = get_active_chart()
    return _get_account_by_code(
        chart=chart, code=_resolve_code(semantic_key="SALES_DISCOUNT", chart=chart)
    )


def get_vat_payable_account() -> Account:
    chart = get_active_chart()
    return _get_account_by_code(
        chart=chart, code=_resolve_code(semantic_key="VAT_PAYABLE", chart=chart)
    )