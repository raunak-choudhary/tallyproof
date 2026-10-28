"""ASGI entry point: HTTP goes to Django, WebSockets to the ledger stream."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402 - needs Django set up
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.realtime.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_app,
        "websocket": AllowedHostsOriginValidator(URLRouter(websocket_urlpatterns)),
    }
)
