"""Django app configuration for ingestion."""

from django.apps import AppConfig


class IngestionConfig(AppConfig):
    """Kafka consumer that validates events and appends them to the ledger."""

    name = "apps.ingestion"
