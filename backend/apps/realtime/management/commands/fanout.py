"""``python manage.py fanout``: broadcast ledger facts from Kafka to WebSocket clients.

Live updates are best effort: the consumer commits automatically, and a client
that misses a fact can always fetch it from the API.
"""

import asyncio
import signal
from types import FrameType

import structlog
from confluent_kafka import Consumer
from django.core.management.base import BaseCommand

from apps.realtime.fanout import broadcast, to_fact
from config.env import app_settings
from config.logging import configure

log = structlog.get_logger(__name__)


class Command(BaseCommand):
    """Run the fan-out worker."""

    help = "Forward appended events, checkpoints, and breaks to connected WebSocket clients."

    def handle(self, *args: object, **options: object) -> None:
        """Run until SIGINT or SIGTERM."""
        configure()
        env = app_settings()
        stopping = False

        def stop(signum: int, frame: FrameType | None) -> None:
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        consumer = Consumer(
            {
                "bootstrap.servers": env.kafka_bootstrap_servers,
                "group.id": "realtime-v1",
                "auto.offset.reset": "latest",
            }
        )
        consumer.subscribe(
            [
                env.kafka_topic_ledger_appended,
                env.kafka_topic_checkpoints,
                env.kafka_topic_recon_breaks,
            ]
        )
        loop = asyncio.new_event_loop()  # one loop for the whole run: one Redis pool
        try:
            while not stopping:
                facts = []
                for message in consumer.consume(num_messages=200, timeout=1.0):
                    topic = message.topic()
                    if message.error() is not None or topic is None:
                        continue
                    fact = to_fact(topic, message.value())
                    if fact is not None:
                        facts.append(fact)
                if facts:
                    loop.run_until_complete(broadcast(facts))
        finally:
            consumer.close()
            loop.close()
