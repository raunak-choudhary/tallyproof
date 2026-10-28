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
    "apps.ingestion",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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

# Browser hardening. The API sets no cookies today; the cookie flags make sure
# any added later can't leak over plain HTTP.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_SSL_REDIRECT = ENV.secure_ssl_redirect
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = ENV.secure_ssl_redirect
SECURE_HSTS_SECONDS = ENV.hsts_seconds
SECURE_HSTS_INCLUDE_SUBDOMAINS = ENV.hsts_seconds > 0
# HSTS preload is deliberately off: getting a domain off the browser preload
# list takes months, so that is a decision for a real deployment, not a default.
SILENCED_SYSTEM_CHECKS = ["security.W021"]
# Behind a TLS-terminating proxy, trust its header for the original scheme.
if ENV.trusted_proxy_count > 0:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
DATA_ROOT = REPO_ROOT / "data"
