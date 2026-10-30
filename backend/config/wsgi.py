"""WSGI entry point."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
application = get_wsgi_application()

from config.tracing import configure_tracing  # noqa: E402 - needs settings loaded first

configure_tracing("tallyproof-api")
