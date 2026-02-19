# users/urls.py

from django.urls import path

from .views import LoginView, MeView, RegisterView

app_name = "users"

urlpatterns = [
    # ---------------- PUBLIC AUTH ----------------
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    # ---------------- AUTHENTICATED ----------------
    path("me/", MeView.as_view(), name="me"),
]
