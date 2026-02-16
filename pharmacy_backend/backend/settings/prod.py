# backend/settings/prod.py
"""
PATH: backend/settings/prod.py

PRODUCTION SETTINGS (Render)

Hardening goals:
- DEBUG off
- Security headers sane
- Proxy SSL header set for Render
- Static collection target set
- CORS/CSRF are explicit (no localhost assumptions)
"""

from __future__ import annotations

from .base import *  # noqa

DEBUG = env.bool("DEBUG", default=False)

# In prod you MUST set these via env vars on Render
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# Static files for collectstatic
STATIC_ROOT = env("STATIC_ROOT", default=str(BASE_DIR / "staticfiles"))

# Render sits behind a proxy: respect X-Forwarded-Proto
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Reasonable cookie security (works fine behind HTTPS)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# If you terminate SSL at the proxy, this keeps Django honest
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)

# HSTS (start modest; increase later)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)

# Tighten common headers
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# CORS/CSRF must be explicit in prod
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Optional WhiteNoise (safe add: only activates if installed)
try:
    import whitenoise  # noqa: F401

    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
except Exception:
    # If whitenoise isn't installed yet, prod can still boot.
    # You can enable it by adding "whitenoise" to requirements later.
    pass