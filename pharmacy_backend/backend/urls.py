# backend/urls.py
"""
PROJECT URLS

All API routes live under /api/

We add PUBLIC ONLINE STORE endpoints under:
- /api/public/...

These endpoints are AllowAny and are used by the storefront.

Operational maturity:
- Add /api/health/ endpoint (AllowAny) that checks DB connectivity.

Security hardening:
- Make Django admin path configurable via env var (ADMIN_PATH)
  to reduce bot scanning/noise and narrow attack surface.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.db import connections
from django.db.utils import OperationalError
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.utils import extend_schema
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


# ------------------ API ROOT (PUBLIC) ------------------
@extend_schema(
    responses={
        200: {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "auth": {"type": "object"},
                "docs": {"type": "object"},
                "modules": {"type": "object"},
            },
        }
    },
)
@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(request):
    return Response(
        {
            "message": "Pharmacy Backend API is running",
            "auth": {
                "register": "/api/auth/register/",
                "login": "/api/auth/login/",
                "me": "/api/auth/me/",
                "jwt_create": "/api/auth/jwt/create/",
                "jwt_refresh": "/api/auth/jwt/refresh/",
            },
            "docs": {
                "swagger": "/api/docs/",
                "schema": "/api/schema/",
            },
            "modules": {
                "products": "/api/products/",
                "store": "/api/store/",
                "sales": "/api/sales/",
                "pos": "/api/pos/",
                "accounting": "/api/accounting/",
                "purchases": "/api/purchases/",
                "public": "/api/public/",
            },
        }
    )


# ------------------ HEALTH CHECK (PUBLIC) ------------------
@extend_schema(
    responses={
        200: {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "db": {"type": "string"},
            },
        },
        503: {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "db": {"type": "string"},
                "error": {"type": "string"},
            },
        },
    },
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """
    Minimal operational endpoint:
    - Confirms app is responding
    - Confirms DB connection + simple query works
    """
    try:
        conn = connections["default"]
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
        return Response({"status": "ok", "db": "ok"})
    except OperationalError as e:
        return Response(
            {"status": "degraded", "db": "down", "error": str(e)}, status=503
        )
    except Exception as e:
        return Response(
            {"status": "degraded", "db": "unknown", "error": str(e)}, status=503
        )


# ------------------ ADMIN PATH (HARDENED) ------------------
# Default is the legacy /admin/ to avoid breaking local setups.
# In production, set ADMIN_PATH to something non-obvious, e.g.:
#   ADMIN_PATH=control-panel-9f3k/
#
# IMPORTANT:
# - Keep trailing slash.
# - Do NOT expose the chosen path in public docs.
ADMIN_PATH = getattr(settings, "ADMIN_PATH", "admin/")
if not ADMIN_PATH.endswith("/"):
    ADMIN_PATH = f"{ADMIN_PATH}/"


# ------------------ API ROUTES (ALL UNDER /api/) ------------------
api_urlpatterns = [
    # Health check / root
    path("", api_root, name="api-root"),
    path("health/", health_check, name="health-check"),
    # OpenAPI / Swagger
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # JWT (SimpleJWT)
    path("auth/jwt/create/", TokenObtainPairView.as_view(), name="jwt-create"),
    path("auth/jwt/refresh/", TokenRefreshView.as_view(), name="jwt-refresh"),
    # Auth & Users
    path("auth/", include("users.urls")),
    # App modules
    path("products/", include("products.urls")),
    path("store/", include("store.urls")),
    # ✅ Sales module (STAFF + backward-compatible public endpoints)
    path("sales/", include("sales.api.urls")),
    path("pos/", include("pos.urls")),
    path("accounting/", include("accounting.api.urls")),
    path("purchases/", include("purchases.api.urls")),
    # ✅ PUBLIC ONLINE STORE (AllowAny)
    path("public/", include("public.urls")),
]

urlpatterns = [
    # Hardened admin path
    path(ADMIN_PATH, admin.site.urls),
    # ✅ Root convenience: visiting / takes you to Swagger docs
    path("", RedirectView.as_view(url="/api/docs/", permanent=False), name="root"),
    path("api/", include(api_urlpatterns)),
]
