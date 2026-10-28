"""Django app configuration for the realtime stream."""

from django.apps import AppConfig


class RealtimeConfig(AppConfig):
    """WebSocket stream of ledger facts."""

    name = "apps.realtime"
