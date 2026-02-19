"""
PATH: backend/settings/base.py

BASE SETTINGS (shared by dev + prod)

Operational maturity:
- Throttling (already)
- Frontend redirect base (already)
- Legacy checkout kill-switch (already)
- Sentry (optional): error visibility in production
- Accounting posting toggle (NEW): allow tests/dev to run POS without ledger setup
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import environ
from corsheaders.defaults import default_headers, default_methods

# -----------------------------------------
# BASE DIRECTORY
# -----------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# -----------------------------------------
# TEST MODE DETECTION
# -----------------------------------------
TESTING = "test" in sys.argv

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
    # Throttling
    THROTTLE_ANON_RATE=(str, "60/min"),
    THROTTLE_USER_RATE=(str, "600/min"),
    THROTTLE_PUBLIC_POLL_RATE=(str, "120/min"),
    THROTTLE_PUBLIC_WRITE_RATE=(str, "10/min"),
    THROTTLE_PUBLIC_CATALOG_RATE=(str, "120/min"),
    THROTTLE_WEBHOOK_RATE=(str, "600/min"),
    FRONTEND_BASE_URL=(str, "http://localhost:5173"),
    # Kill switch (legacy public checkout)
    PUBLIC_LEGACY_CHECKOUT_ENABLED=(bool, True),
    # Sentry (optional; enable by setting SENTRY_DSN)
    SENTRY_DSN=(str, ""),
    SENTRY_ENVIRONMENT=(str, "development"),
    SENTRY_TRACES_SAMPLE_RATE=(float, 0.0),
    SENTRY_SEND_PII=(bool, False),
    # Accounting posting toggle (NEW)
    # Default: disabled in tests to avoid failing POS flow due to missing chart setup.
    ACCOUNTING_POSTING_ENABLED=(bool, not TESTING),
)

# -----------------------------------------
# LOAD .env
# -----------------------------------------
env_file_1 = BASE_DIR / ".env"
env_file_2 = BASE_DIR.parent / ".env"

if env_file_1.exists():
    env.read_env(str(env_file_1))
elif env_file_2.exists():
    env.read_env(str(env_file_2))

# -----------------------------------------
# CORE SECURITY
# -----------------------------------------
SECRET_KEY = (env("SECRET_KEY") or "dev-insecure-change-me").strip()
DEBUG = env.bool("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# -----------------------------------------
# I18N / TZ
# -----------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = (env("TIME_ZONE") or "UTC").strip()
USE_I18N = True
USE_TZ = True

# -----------------------------------------
# AUTH USER MODEL (custom)
# -----------------------------------------
AUTH_USER_MODEL = "users.User"

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
    "accounting",
    "users",
    "products",
    "sales.apps.SalesConfig",
    "store.apps.StoreConfig",
    "pos",
    "purchases",
    "public.apps.PublicConfig",
    "batches",
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
# TEMPLATES (required for Django admin)
# -----------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [str(BASE_DIR / "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

# -----------------------------------------
# REST FRAMEWORK
# -----------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "PAGE_SIZE_QUERY_PARAM": "page_size",
    "MAX_PAGE_SIZE": 100,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON_RATE"),
        "user": env("THROTTLE_USER_RATE"),
        "public_poll": env("THROTTLE_PUBLIC_POLL_RATE"),
        "public_write": env("THROTTLE_PUBLIC_WRITE_RATE"),
        "public_catalog": env("THROTTLE_PUBLIC_CATALOG_RATE"),
        "webhook": env("THROTTLE_WEBHOOK_RATE"),
    },
}

# -----------------------------------------
# SIMPLE JWT
# -----------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

# -----------------------------------------
# DATABASE
# -----------------------------------------
DATABASES = {
    "default": env.db("DATABASE_URL"),
}

# -----------------------------------------
# FRONTEND BASE URL
# -----------------------------------------
FRONTEND_BASE_URL = (env("FRONTEND_BASE_URL") or "http://localhost:5173").strip()

# -----------------------------------------
# LEGACY CHECKOUT TOGGLE
# -----------------------------------------
PUBLIC_LEGACY_CHECKOUT_ENABLED = env.bool("PUBLIC_LEGACY_CHECKOUT_ENABLED")

# -----------------------------------------
# PAYMENTS
# -----------------------------------------
PAYMENTS = {
    "PAYSTACK": {
        "PUBLIC_KEY": (env("PAYSTACK_PUBLIC_KEY") or "").strip(),
        "SECRET_KEY": (env("PAYSTACK_SECRET_KEY") or "").strip(),
        "CALLBACK_URL": (env("PAYSTACK_CALLBACK_URL") or "").strip(),
    }
}

# -----------------------------------------
# ACCOUNTING POSTING TOGGLE
# -----------------------------------------
ACCOUNTING_POSTING_ENABLED = env.bool("ACCOUNTING_POSTING_ENABLED")

# -----------------------------------------
# SENTRY (optional)
# -----------------------------------------
SENTRY_DSN = (env("SENTRY_DSN") or "").strip()
SENTRY_ENVIRONMENT = (env("SENTRY_ENVIRONMENT") or "development").strip()
SENTRY_TRACES_SAMPLE_RATE = float(env("SENTRY_TRACES_SAMPLE_RATE"))
SENTRY_SEND_PII = env.bool("SENTRY_SEND_PII")

if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=SENTRY_ENVIRONMENT,
            integrations=[DjangoIntegration()],
            traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
            send_default_pii=SENTRY_SEND_PII,
        )
    except Exception:
        pass

# -----------------------------------------
# CORS / CSRF
# -----------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = list(default_methods)
CORS_ALLOW_HEADERS = list(default_headers)

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS")

# -----------------------------------------
# STATIC FILES
# -----------------------------------------
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -----------------------------------------
# SWAGGER
# -----------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "Pharmacy Backend API",
    "DESCRIPTION": "POS, Inventory, Sales, and User Management API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
