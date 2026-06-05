from django.urls import path, include
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

# ------------------ API ROOT ------------------
@api_view(["GET"])
def api_root(request):
    """
    Simple API root endpoint to verify backend is running.
    """
    return Response({
        "message": "Pharmacy Backend API is running",
        "auth": {
            "register": "/auth/register/",
            "login": "/auth/login/",
            "me": "/auth/me/",
            "jwt_create": "/auth/jwt/create/",
            "jwt_refresh": "/auth/jwt/refresh/",
        },
        "docs": {
            "swagger": "/api/docs/",
            "schema": "/schema/",
        },
        "modules": {
            "users": "/users/",
            "products": "/products/",
            "batches": "/batches/",
            "store": "/store/",
            "sales": "/sales/",
            "pos": "/pos/",
        }
    })

# ------------------ URL ROUTES ------------------
urlpatterns = [
    path("", api_root),

    # OpenAPI / Swagger
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),

    # JWT token endpoints
    path("auth/jwt/create/", TokenObtainPairView.as_view(), name="jwt-create"),
    path("auth/jwt/refresh/", TokenRefreshView.as_view(), name="jwt-refresh"),

    # Auth & users
    path("auth/", include("users.urls")),
    path("users/", include("users.urls")),

    # App modules
    path("products/", include("products.urls")),
    path("batches/", include("batches.urls")),
    path("store/", include("store.urls")),
    path("sales/", include("sales.urls")),
    path("pos/", include("pos.urls")),
]
