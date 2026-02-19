# backend/settings/prod.py
"""
PATH: backend/settings/prod.py

PRODUCTION SETTINGS (Render)

Hardening goals (FINISHING MOVE):
- DEBUG off (forced)
- SECRET_KEY must be set (fail-closed)
- Postgres-only (NO sqlite fallback)
- Security headers sane
- Proxy SSL header set for Render
- Static collection target set
- CORS/CSRF are explicit (no localhost assumptions, https only)
- Cookie flags hardened
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import BASE_DIR, MIDDLEWARE, env  # explicit for Ruff (F405)

# ----------------------------
# DEBUG (force off)
# ----------------------------
DEBUG = False

# ----------------------------
# SECRET KEY (fail closed)
# ----------------------------
_secret_key = (env("SECRET_KEY", default="") or "").strip()
if not _secret_key or _secret_key == "dev-insecure-change-me":
    raise ImproperlyConfigured(
        "SECRET_KEY must be set to a strong value in production."
    )
SECRET_KEY = _secret_key

# ----------------------------
# Hosts (must be set on Render)
# ----------------------------
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set in production.")

# ----------------------------
# Database (Render Managed Postgres) — POSTGRES ONLY
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

# ----------------------------
# Static files (collectstatic)
# ----------------------------
STATIC_ROOT = env("STATIC_ROOT", default=str(BASE_DIR / "staticfiles"))

# WhiteNoise (static serving)
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ----------------------------
# Proxy / SSL (Render sits behind a proxy)
# ----------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)

# HSTS (start modest; can increase later)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=True,
)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)

# ----------------------------
# Cookie hardening
# ----------------------------
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# ----------------------------
# Security headers
# ----------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# ----------------------------
# CORS / CSRF (explicit + https only)
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
    raise ImproperlyConfigured("CORS_ALLOWED_ORIGINS must be https:// in production.")
if any(o.startswith("http://") for o in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured("CSRF_TRUSTED_ORIGINS must be https:// in production.")

CORS_ALLOW_CREDENTIALS = False
