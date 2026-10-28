"""``python manage.py relay_outbox``: publish outbox messages to Kafka."""

import logging
import signal
from types import FrameType

import psycopg
from confluent_kafka import Producer
from django.core.management.base import BaseCommand
from django.db import connection

from apps.ledger.outbox import RelayError, relay_batch
from apps.ledger.projections import OUTBOX_CHANNEL
from config.env import app_settings
from config.logging import configure

log = logging.getLogger(__name__)
IDLE_WAIT_SECONDS = 5.0


class Command(BaseCommand):
    """Run the outbox relay."""

    help = "Publish committed outbox messages to Kafka, at least once and in order."

    def handle(self, *args: object, **options: object) -> None:
        """Run until SIGINT or SIGTERM."""
        configure()
        stopping = False

        def stop(signum: int, frame: FrameType | None) -> None:
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        producer = Producer(
            {
                "bootstrap.servers": app_settings().kafka_bootstrap_servers,
                "acks": "all",
                "enable.idempotence": True,
                "linger.ms": 20,
            }
        )
        settings = connection.settings_dict
        with psycopg.connect(
            dbname=settings["NAME"],
            user=settings["USER"],
            password=settings["PASSWORD"],
            host=settings["HOST"],
            port=settings["PORT"] or 5432,
            autocommit=True,
        ) as listener:
            listener.execute(f"LISTEN {OUTBOX_CHANNEL}")
            while not stopping:
                try:
                    published = relay_batch(producer)
                except RelayError as error:
                    log.warning("batch not published, retrying: %s", error)
                    published = 0
                if published:
                    log.info("published %d outbox messages", published)
                    continue
                for _ in listener.notifies(timeout=IDLE_WAIT_SECONDS, stop_after=1):
                    pass
