# store/urls.py

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from store.views import StoreViewSet

router = DefaultRouter()
router.register(r"stores", StoreViewSet, basename="stores")

urlpatterns = [
    path("", include(router.urls)),
]
