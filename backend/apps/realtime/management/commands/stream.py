"""``manage.py stream``: serve the WebSocket endpoint with its limits from settings."""

import uvicorn
from django.core.management.base import BaseCommand

from config.env import app_settings


class Command(BaseCommand):
    """Run the ASGI app under Uvicorn."""

    help = "Serve /ws/v1/stream with the host, port, and frame size from settings."

    def handle(self, *args: object, **options: object) -> None:
        """Serve until interrupted."""
        settings = app_settings()
        uvicorn.run(
            "config.asgi:application",
            host=settings.stream_host,
            port=settings.stream_port,
            ws_max_size=settings.ws_max_message_bytes,
            log_level=settings.log_level.lower(),
            # Client addresses key the per-IP connection cap, so forwarded headers
            # count only when a proxy is configured in front (TRUSTED_PROXY_COUNT).
            proxy_headers=settings.trusted_proxy_count > 0,
        )
