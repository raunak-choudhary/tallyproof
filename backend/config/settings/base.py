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
    "channels",
    "apps.health",
    "apps.ledger",
    "apps.ingestion",
    "apps.reconciliation",
    "apps.realtime",
]

# Live updates fan out through Redis. Each WebSocket client drains the group into
# its own small buffer, so a slow client drops its oldest facts instead of
# slowing everyone down (apps/realtime/consumers.py).
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [ENV.redis_url], "capacity": 200, "expiry": 30},
    }
}

# Rate-limit counters. Per process for now; a shared cache arrives with Redis.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

MIDDLEWARE = [
    "config.middleware.CorrelationIdMiddleware",
    "config.middleware.ContentSecurityPolicyMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Only the API docs page renders a template (drf-spectacular's Swagger viewer).
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
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
CORS_EXPOSE_HEADERS = ["X-Correlation-ID"]

# Logs are JSON lines configured in config.logging; Django adds nothing of its own.
LOGGING_CONFIG = None

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": ENV.api_throttle_anon_reads},
    "NUM_PROXIES": ENV.trusted_proxy_count,
    "EXCEPTION_HANDLER": "apps.ledger.api.problems.handler",
}

# The docs page loads the Swagger viewer from its CDN, pinned to one version
# rather than drf-spectacular's default of "latest".
SWAGGER_UI_VERSION = "5.33.2"
SWAGGER_UI_CDN = f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{SWAGGER_UI_VERSION}"

SPECTACULAR_SETTINGS = {
    "TITLE": "Tallyproof API",
    "DESCRIPTION": "Ledger events, Merkle proofs, and signed checkpoints. "
    "The API returns proofs; clients do the verifying.",
    "VERSION": "1.0.0",
    "SWAGGER_UI_DIST": SWAGGER_UI_CDN,
    "SWAGGER_UI_FAVICON_HREF": f"{SWAGGER_UI_CDN}/favicon-32x32.png",
}

# Browser hardening. The API sets no cookies today; the cookie flags make sure
# any added later can't leak over plain HTTP.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# The API serves JSON, so nothing may load or frame it. The docs page may load the
# Swagger viewer from its CDN (SWAGGER_UI_CDN, above).
CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'"
CONTENT_SECURITY_POLICY_DOCS = (
    "default-src 'none'; frame-ancestors 'none'; connect-src 'self';"
    " script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net;"
    " style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net;"
    " img-src 'self' data: https://cdn.jsdelivr.net"
)
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
