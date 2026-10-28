"""Django app configuration for the analyst."""

from django.apps import AppConfig


class AnalystConfig(AppConfig):
    """Curated read-only views, the query compiler, and the answer pipeline."""

    name = "apps.analyst"
