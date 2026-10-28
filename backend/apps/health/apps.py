"""Django app configuration for health checks."""

from django.apps import AppConfig


class HealthConfig(AppConfig):
    """Liveness and readiness endpoints."""

    name = "apps.health"
