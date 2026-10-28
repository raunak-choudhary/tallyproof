"""WebSocket routes."""

from typing import Any, cast

from django.urls import path

from apps.realtime.consumers import LedgerStreamConsumer

# Django's path() is typed for HTTP views; Channels routes ASGI apps through it too.
websocket_urlpatterns: list[Any] = [
    path("ws/v1/stream", cast("Any", LedgerStreamConsumer.as_asgi())),
]
