"""
PATH: backend/settings/prod.py

PRODUCTION SETTINGS (Render)

HARDENED FINAL VERSION
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import BASE_DIR, MIDDLEWARE, env  # explicit import


# ----------------------------
# DEBUG (FORCED OFF)
# ----------------------------
DEBUG = False


# ----------------------------
# SECRET KEY (FAIL CLOSED)
# ----------------------------
_secret_key = (env("SECRET_KEY", default="") or "").strip()
if not _secret_key or _secret_key == "dev-insecure-change-me":
    raise ImproperlyConfigured(
        "SECRET_KEY must be set to a strong value in production."
    )
SECRET_KEY = _secret_key


# ----------------------------
# ALLOWED HOSTS (REQUIRED)
# ----------------------------
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set in production.")


# ----------------------------
# DATABASE (POSTGRES ONLY)
# ----------------------------
database_url_raw = (env("DATABASE_URL", default="") or "").strip()
if not database_url_raw:
    raise ImproperlyConfigured(
        "DATABASE_URL must be set in production (Render Postgres)."
    )

if database_url_raw.startswith("sqlite"):
    raise ImproperlyConfigured(
        "Refusing to start in production with SQLite DATABASE_URL."
    )

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True


# ----------------------------
# STATIC FILES
# ----------------------------
STATIC_ROOT = env("STATIC_ROOT", default=str(BASE_DIR / "staticfiles"))

MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# ----------------------------
# PROXY / SSL (RENDER)
# ----------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = []


# ----------------------------
# HSTS (FULL HARDENING)
# ----------------------------
# 1 year required for preload
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True


# ----------------------------
# COOKIE HARDENING
# ----------------------------
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"


# ----------------------------
# SECURITY HEADERS
# ----------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True  # backward compatibility header
SECURE_REFERRER_POLICY = "strict-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_RESOURCE_POLICY = "same-origin"


# ----------------------------
# CORS / CSRF (HTTPS ONLY)
# ----------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

if not CORS_ALLOWED_ORIGINS:
    raise ImproperlyConfigured("CORS_ALLOWED_ORIGINS must be set in production.")

if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured("CSRF_TRUSTED_ORIGINS must be set in production.")

if any("localhost" in o or "127.0.0.1" in o for o in CORS_ALLOWED_ORIGINS):
    raise ImproperlyConfigured(
        "Remove localhost from CORS_ALLOWED_ORIGINS in production."
    )

if any("localhost" in o or "127.0.0.1" in o for o in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured(
        "Remove localhost from CSRF_TRUSTED_ORIGINS in production."
    )

if any(o.startswith("http://") for o in CORS_ALLOWED_ORIGINS):
    raise ImproperlyConfigured(
        "CORS_ALLOWED_ORIGINS must use https:// in production."
    )

if any(o.startswith("http://") for o in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured(
        "CSRF_TRUSTED_ORIGINS must use https:// in production."
    )

CORS_ALLOW_CREDENTIALS = False


import logging
import sys


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "structured": {
            "format": (
                "{asctime} | {levelname} | {name} | "
                "{message}"
            ),
            "style": "{",
        },
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "structured",
        },
    },

    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },

    "loggers": {
        # Django internal errors
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },

        # Payment logic
        "payments": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },

        # Webhooks
        "webhooks": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },

        # Accounting / journal posting
        "accounting": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}