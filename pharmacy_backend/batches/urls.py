# batches/urls.py
from rest_framework.routers import DefaultRouter
from batches.views import BatchViewSet

router = DefaultRouter()
router.register(r"batches", BatchViewSet, basename="batches")

urlpatterns = router.urls
