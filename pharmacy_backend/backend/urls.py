# backend/urls.py
"""
PROJECT URLS

All API routes live under /api/

We add PUBLIC ONLINE STORE endpoints under:
- /api/public/...

These endpoints are AllowAny and are used by the storefront.
"""

from django.contrib import admin
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


# ------------------ API ROUTES (ALL UNDER /api/) ------------------
api_urlpatterns = [
    # Health check / root
    path("", api_root, name="api-root"),
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
    path("admin/", admin.site.urls),
    # ✅ Root convenience: visiting / takes you to Swagger docs
    path("", RedirectView.as_view(url="/api/docs/", permanent=False), name="root"),
    path("api/", include(api_urlpatterns)),
]