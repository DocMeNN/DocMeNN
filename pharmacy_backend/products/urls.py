from rest_framework.routers import DefaultRouter
from .views import ProductViewSet

"""
Products API Routes

Automatically provides:
- GET    /products/products/
- POST   /products/products/
- GET    /products/products/{id}/
- PUT    /products/products/{id}/
- PATCH  /products/products/{id}/
- DELETE /products/products/{id}/

Custom actions:
- POST   /products/products/bulk-create/
"""

router = DefaultRouter()
router.register(
    r"products",
    ProductViewSet,
    basename="products"
)

urlpatterns = router.urls
