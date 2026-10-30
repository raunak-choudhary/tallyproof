"""``python manage.py register_schemas``: register the committed event schema."""

import requests
from django.core.management.base import BaseCommand, CommandError

from apps.ingestion.schemas import SCHEMA_FILE, is_compatible, register, schema_text, subject_for
from config.env import app_settings


class Command(BaseCommand):
    """Register the event schema with BACKWARD compatibility."""

    help = "Register the committed event schema for the raw topic, refusing breaking changes."

    def handle(self, *args: object, **options: object) -> None:
        """Check the file is current, then register it."""
        committed = SCHEMA_FILE.read_text(encoding="utf-8")
        if committed != schema_text():
            raise CommandError(f"{SCHEMA_FILE.name} is out of date; run make schemas and review it")
        env = app_settings()
        subject = subject_for(env.kafka_topic_events_raw)
        registry = env.kafka_schema_registry_url
        try:
            compatible = is_compatible(registry, subject, committed)
        except requests.HTTPError as error:
            # A subject with no versions yet has nothing to break; anything else is a real failure.
            if error.response is None or error.response.status_code != 404:
                raise
            compatible = True
        if not compatible:
            raise CommandError(f"the schema is not backward compatible with {subject}'s latest")
        schema_id = register(registry, subject, committed)
        self.stdout.write(f"{subject} registered as schema {schema_id}, BACKWARD compatibility")
