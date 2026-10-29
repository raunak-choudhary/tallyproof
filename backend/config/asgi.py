"""ASGI entry point for the stream server: WebSockets only.

The HTTP API runs under Gunicorn (``config.wsgi``), with its own workers, limits,
and throttles. This process answers every plain HTTP request with 404, so the API
can't be reached through it around those limits.
"""

import os
from typing import Any

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
get_asgi_application()  # sets Django up before the consumers are imported

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402 - needs Django set up
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.realtime.routing import websocket_urlpatterns  # noqa: E402


async def no_http(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
    """Answer any HTTP request with 404 and an empty body."""
    await send({"type": "http.response.start", "status": 404, "headers": []})
    await send({"type": "http.response.body", "body": b""})


application = ProtocolTypeRouter(
    {
        "http": no_http,
        "websocket": AllowedHostsOriginValidator(URLRouter(websocket_urlpatterns)),
    }
)
