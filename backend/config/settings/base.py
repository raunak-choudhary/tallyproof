"""Settings shared by every environment. Values come from ``config.env``."""

import dj_database_url

from config.env import REPO_ROOT, app_settings

ENV = app_settings()

SECRET_KEY = ENV.secret_key.get_secret_value()
DEBUG = ENV.debug
ALLOWED_HOSTS = ENV.allowed_host_list

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "apps.health",
    "apps.ledger",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": dj_database_url.parse(ENV.db_url.get_secret_value(), conn_max_age=60),
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"

CORS_ALLOWED_ORIGINS = ENV.cors_origin_list

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Tallyproof API",
    "DESCRIPTION": "Ledger events, Merkle proofs, and signed checkpoints. "
    "The API returns proofs; clients do the verifying.",
    "VERSION": "1.0.0",
}

SECURE_CONTENT_TYPE_NOSNIFF = True
REFERRER_POLICY = "same-origin"
DATA_ROOT = REPO_ROOT / "data"
