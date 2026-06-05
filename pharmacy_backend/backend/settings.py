"""
Django settings for backend project.
"""

from pathlib import Path
from corsheaders.defaults import default_headers, default_methods

# -----------------------------------------
# BASE DIRECTORY
# -----------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-_1xs2%)k3@x^j2agw10bs$(c)0z+s2@qey4(98&j@h8f9x+f^='
DEBUG = True

# -----------------------------------------
# HOSTS
# -----------------------------------------
ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
]

# -----------------------------------------
# INSTALLED APPS
# -----------------------------------------
INSTALLED_APPS = [
    'corsheaders',

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt',
    'drf_spectacular',

    'users',
    'products',
    'sales.apps.SalesConfig',
    'store',
    'pos',
]

# -----------------------------------------
# MIDDLEWARE  (ORDER IS CRITICAL)
# -----------------------------------------
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # MUST be first
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',

    # CSRF stays ON (we exempt only specific views)
    'django.middleware.csrf.CsrfViewMiddleware',

    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'backend.urls'

APPEND_SLASH = False

# -----------------------------------------
# REST FRAMEWORK
# -----------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.AllowAny',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# -----------------------------------------
# USER MODEL
# -----------------------------------------
AUTH_USER_MODEL = 'users.User'

AUTHENTICATION_BACKENDS = [
    "users.backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# -----------------------------------------
# TEMPLATES
# -----------------------------------------
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

# -----------------------------------------
# DATABASE
# -----------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# -----------------------------------------
# PASSWORD VALIDATION
# -----------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# -----------------------------------------
# I18N
# -----------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# -----------------------------------------
# STATIC
# -----------------------------------------
STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# -----------------------------------------
# ✅ CORS — FINAL, CORRECT CONFIG
# -----------------------------------------

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
]

CORS_ALLOW_CREDENTIALS = True

# ✅ THIS IS THE MISSING PIECE
CORS_ALLOW_METHODS = list(default_methods) + [
    "OPTIONS",
]

CORS_ALLOW_HEADERS = list(default_headers) + [
    "authorization",
    "content-type",
]

# ✅ Ensure headers are added to OPTIONS responses
CORS_EXPOSE_HEADERS = [
    "Content-Type",
    "Authorization",
]

# -----------------------------------------
# CSRF
# -----------------------------------------
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
]

# -----------------------------------------
# SWAGGER
# -----------------------------------------
SPECTACULAR_SETTINGS = {
    'TITLE': 'Pharmacy Backend API',
    'DESCRIPTION': 'POS, Inventory, Sales, and User Management API',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}
