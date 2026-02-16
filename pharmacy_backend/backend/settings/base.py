# backend/settings/base.py
"""
PATH: backend/settings/base.py

BASE SETTINGS (shared by dev + prod)

Phase 4/5 Hardening:
- Environment variables for secrets (django-environ)
- Paystack configuration under settings.PAYMENTS["PAYSTACK"]
- Backend authoritative totals (frontend never calculates money)

ENV LOADING (AIRTIGHT):
- Reads .env from:
  1) BASE_DIR/.env              (e.g. pharmacy_backend/.env)
  2) BASE_DIR.parent/.env       (e.g. pharmacy_app/.env)
This supports both common project layouts safely.
"""

from __future__ import annotations

from pathlib import Path
from datetime import timedelta

import environ
from corsheaders.defaults import default_headers, default_methods

# -----------------------------------------
# BASE DIRECTORY
# -----------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # -> pharmacy_backend/

# -----------------------------------------
# ENV (django-environ)
# -----------------------------------------
env = environ.Env(
    DEBUG=(bool, True),
    SECRET_KEY=(str, ""),
    TIME_ZONE=(str, "UTC"),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:5173"]),
    CSRF_TRUSTED_ORIGINS=(list, ["http://localhost:5173"]),
    DATABASE_URL=(str, f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
    PAYSTACK_SECRET_KEY=(str, ""),
    PAYSTACK_PUBLIC_KEY=(str, ""),
    PAYSTACK_CALLBACK_URL=(str, ""),
)

# -----------------------------------------
# LOAD .env (AIRTIGHT: support both layouts)
# -----------------------------------------
env_file_1 = BASE_DIR / ".env"          # pharmacy_backend/.env
env_file_2 = BASE_DIR.parent / ".env"   # pharmacy_app/.env

if env_file_1.exists():
    env.read_env(str(env_file_1))
elif env_file_2.exists():
    env.read_env(str(env_file_2))

# -----------------------------------------
# SECURITY (shared; prod hardens further)
# -----------------------------------------
SECRET_KEY = (env("SECRET_KEY") or "dev-insecure-change-me").strip()
DEBUG = env.bool("DEBUG")

# -----------------------------------------
# HOSTS
# -----------------------------------------
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# -----------------------------------------
# INSTALLED APPS
# -----------------------------------------
INSTALLED_APPS = [
    "corsheaders",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "django_filters",
    # Internal apps
    "accounting",
    "users",
    "products",
    "sales.apps.SalesConfig",
    "store.apps.StoreConfig",
    "pos",
    "purchases",
    # Public Online Store module (AllowAny)
    "public.apps.PublicConfig",
]

# -----------------------------------------
# MIDDLEWARE
# -----------------------------------------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.urls"
WSGI_APPLICATION = "backend.wsgi.application"
APPEND_SLASH = True

# -----------------------------------------
# REST FRAMEWORK
# -----------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "PAGE_SIZE_QUERY_PARAM": "page_size",
    "MAX_PAGE_SIZE": 100,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# -----------------------------------------
# SIMPLE JWT
# -----------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# -----------------------------------------
# USER MODEL & AUTH
# -----------------------------------------
AUTH_USER_MODEL = "users.User"

AUTHENTICATION_BACKENDS = [
    "users.backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# -----------------------------------------
# TEMPLATES
# -----------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# -----------------------------------------
# DATABASE
# -----------------------------------------
DATABASES = {
    "default": env.db("DATABASE_URL"),
}

# -----------------------------------------
# PASSWORD VALIDATION
# -----------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# -----------------------------------------
# I18N
# -----------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE")
USE_I18N = True
USE_TZ = True

# -----------------------------------------
# STATIC FILES (prod adds STATIC_ROOT)
# -----------------------------------------
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -----------------------------------------
# CORS CONFIG
# -----------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = list(default_methods)
CORS_ALLOW_HEADERS = list(default_headers)

# -----------------------------------------
# CSRF
# -----------------------------------------
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS")

# -----------------------------------------
# PAYMENTS (PHASE 4)
# -----------------------------------------
PAYMENTS = {
    "PAYSTACK": {
        "PUBLIC_KEY": (env("PAYSTACK_PUBLIC_KEY") or "").strip(),
        "SECRET_KEY": (env("PAYSTACK_SECRET_KEY") or "").strip(),
        "CALLBACK_URL": (env("PAYSTACK_CALLBACK_URL") or "").strip(),
    }
}

# -----------------------------------------
# SWAGGER / OPENAPI
# -----------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "Pharmacy Backend API",
    "DESCRIPTION": "POS, Inventory, Sales, and User Management API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}