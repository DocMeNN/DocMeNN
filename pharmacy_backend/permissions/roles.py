# permissions/roles.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from rest_framework.permissions import BasePermission


# =========================================================
# ROLE CONSTANTS (STAFF JOB ROLES)
# =========================================================
# These are NOT business types.
# They describe what the staff member does.
ROLE_ADMIN = "admin"
ROLE_PHARMACIST = "pharmacist"
ROLE_CASHIER = "cashier"
ROLE_RECEPTION = "reception"

# Optional future expansion (safe to add now)
ROLE_MANAGER = "manager"  # supervisor/store manager (recommended)

STAFF_ROLES = {
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_PHARMACIST,
    ROLE_CASHIER,
    ROLE_RECEPTION,
}


# =========================================================
# BUSINESS TYPE CONSTANTS (TENANT CONFIG)
# =========================================================
# This is the "pharmacy vs supermarket vs general retail" selector.
# You typically store this on a Tenant/Business model, not on User.
BUSINESS_PHARMACY = "pharmacy"
BUSINESS_SUPERMARKET = "supermarket"
BUSINESS_RETAIL = "retail"

BUSINESS_TYPES = {
    BUSINESS_PHARMACY,
    BUSINESS_SUPERMARKET,
    BUSINESS_RETAIL,
}


# =========================================================
# CAPABILITIES (THE REAL PERMISSION LANGUAGE)
# =========================================================
# Think of these as features/actions.
# Views should protect capabilities, not raw roles.
CAP_POS_SELL = "pos.sell"
CAP_POS_REFUND = "pos.refund"
CAP_POS_VOID = "pos.void"

CAP_REPORTS_VIEW_POS = "reports.view_pos"
CAP_REPORTS_VIEW_ACCOUNTING = "reports.view_accounting"

CAP_ACCOUNTING_POST = "accounting.post"       # opening balances, expenses, closing
CAP_ACCOUNTING_CLOSE = "accounting.close"     # closing period, lock/unlock

CAP_INVENTORY_VIEW = "inventory.view"
CAP_INVENTORY_EDIT = "inventory.edit"
CAP_INVENTORY_ADJUST = "inventory.adjust"     # sensitive manual adjustments

CAP_PHARMACY_DISPENSE = "pharmacy.dispense"
CAP_PHARMACY_CONTROLLED = "pharmacy.controlled"

CAP_AUDIT_VIEW = "audit.view"
CAP_AUDIT_WRITE = "audit.write"

ALL_CAPABILITIES = {
    CAP_POS_SELL,
    CAP_POS_REFUND,
    CAP_POS_VOID,
    CAP_REPORTS_VIEW_POS,
    CAP_REPORTS_VIEW_ACCOUNTING,
    CAP_ACCOUNTING_POST,
    CAP_ACCOUNTING_CLOSE,
    CAP_INVENTORY_VIEW,
    CAP_INVENTORY_EDIT,
    CAP_INVENTORY_ADJUST,
    CAP_PHARMACY_DISPENSE,
    CAP_PHARMACY_CONTROLLED,
    CAP_AUDIT_VIEW,
    CAP_AUDIT_WRITE,
}


# =========================================================
# ROLE → CAPABILITY MAP (DEFAULT)
# =========================================================
# Default capabilities per role, independent of business type.
# Business type will optionally narrow/override below.
ROLE_CAPABILITIES: dict[str, set[str]] = {
    ROLE_ADMIN: {
        # admin can do everything
        *ALL_CAPABILITIES,
    },
    ROLE_MANAGER: {
        CAP_POS_SELL,
        CAP_POS_REFUND,
        CAP_POS_VOID,
        CAP_REPORTS_VIEW_POS,
        CAP_INVENTORY_VIEW,
        CAP_INVENTORY_EDIT,
        # usually NOT inventory.adjust unless you want managers to do it
    },
    ROLE_CASHIER: {
        CAP_POS_SELL,
        # deliberately NOT refund/void, unless you decide otherwise
    },
    ROLE_PHARMACIST: {
        CAP_INVENTORY_VIEW,
        CAP_INVENTORY_EDIT,
        CAP_PHARMACY_DISPENSE,
        CAP_PHARMACY_CONTROLLED,
        CAP_REPORTS_VIEW_POS,
    },
    ROLE_RECEPTION: {
        # reception is not used much in retail, but keeping it for your platform
        # (pharmacy clinic workflows etc.)
    },
}


# =========================================================
# BUSINESS TYPE OVERRIDES (OPTIONAL)
# =========================================================
# If a business type doesn't support a capability, we can strip it here.
# Example: supermarket doesn't need pharmacy capabilities.
BUSINESS_DISABLED_CAPABILITIES: dict[str, set[str]] = {
    BUSINESS_PHARMACY: set(),  # everything allowed if role has it
    BUSINESS_SUPERMARKET: {
        CAP_PHARMACY_DISPENSE,
        CAP_PHARMACY_CONTROLLED,
    },
    BUSINESS_RETAIL: {
        CAP_PHARMACY_DISPENSE,
        CAP_PHARMACY_CONTROLLED,
    },
}


# =========================================================
# Helpers
# =========================================================
def get_user_role(user) -> Optional[str]:
    return getattr(user, "role", None)


def get_request_business_type(request) -> Optional[str]:
    """
    Multi-business support hook.

    Recommended future design:
    - request.tenant.business_type OR
    - request.business.business_type OR
    - user.tenant.business_type

    For now, we try common patterns safely.
    """
    tenant = getattr(request, "tenant", None) or getattr(request, "business", None)
    if tenant:
        bt = getattr(tenant, "business_type", None) or getattr(tenant, "type", None)
        if bt in BUSINESS_TYPES:
            return bt

    user = getattr(request, "user", None)
    if user:
        bt = getattr(user, "business_type", None)
        if bt in BUSINESS_TYPES:
            return bt

    return None


def effective_capabilities_for(request, user) -> set[str]:
    """
    Compute capabilities from role, then apply business type restrictions.
    """
    role = get_user_role(user)
    caps = set(ROLE_CAPABILITIES.get(role, set()))

    bt = get_request_business_type(request)
    if bt:
        disabled = BUSINESS_DISABLED_CAPABILITIES.get(bt, set())
        caps = caps - disabled

    return caps


# =========================================================
# Base Role Permission (Internal Use)
# =========================================================
class BaseRolePermission(BasePermission):
    """
    Base permission for role-based access control.

    Subclasses must define:
    - allowed_roles (set)
    """

    allowed_roles: set[str] = set()

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        user_role = get_user_role(user)
        if not user_role:
            return False

        return user_role in self.allowed_roles


# =========================================================
# Capability Permissions (RECOMMENDED FOR NEW CODE)
# =========================================================
@dataclass(frozen=True)
class _CapabilitySpec:
    all_of: set[str]
    any_of: set[str]


class HasCapability(BasePermission):
    """
    Require a specific capability.

    Usage:
        permission_classes = [IsAuthenticated, HasCapability]
        view.required_capability = CAP_POS_REFUND
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        required = getattr(view, "required_capability", None)
        if not required:
            # If not set, deny-by-default to avoid accidental open endpoints
            return False

        caps = effective_capabilities_for(request, user)
        return required in caps


class HasAnyCapability(BasePermission):
    """
    Require ANY capability from a list.

    Usage:
        view.required_any_capabilities = {CAP_REPORTS_VIEW_POS, CAP_REPORTS_VIEW_ACCOUNTING}
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        required = getattr(view, "required_any_capabilities", None)
        if not required:
            return False

        caps = effective_capabilities_for(request, user)
        return any(cap in caps for cap in set(required))


class HasAllCapabilities(BasePermission):
    """
    Require ALL capabilities in a list.

    Usage:
        view.required_all_capabilities = {CAP_ACCOUNTING_POST, CAP_AUDIT_WRITE}
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        required = getattr(view, "required_all_capabilities", None)
        if not required:
            return False

        caps = effective_capabilities_for(request, user)
        return set(required).issubset(caps)


# =========================================================
# Backward-Compatible Role Permissions (KEEPING YOUR API)
# =========================================================
class IsAdmin(BaseRolePermission):
    allowed_roles = {ROLE_ADMIN}


class IsPharmacist(BaseRolePermission):
    allowed_roles = {ROLE_PHARMACIST}


class IsPharmacistOrAdmin(BaseRolePermission):
    allowed_roles = {ROLE_PHARMACIST, ROLE_ADMIN}


class IsCashier(BaseRolePermission):
    allowed_roles = {ROLE_CASHIER}


class IsReception(BaseRolePermission):
    allowed_roles = {ROLE_RECEPTION}


class IsStaff(BaseRolePermission):
    allowed_roles = STAFF_ROLES
