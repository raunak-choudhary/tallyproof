"""``python manage.py ingest``: run the ingestion consumer until interrupted."""

import logging
import signal
from types import FrameType

from confluent_kafka import Consumer
from django.core.management.base import BaseCommand

from apps.ingestion.consumer import Ingestor, producer_for_dead_letters, run
from apps.ingestion.dedupe import PartitionFilters
from config.env import app_settings


class Command(BaseCommand):
    """Consume raw events into the ledger."""

    help = "Consume raw events from Kafka into the ledger, exactly once."

    def handle(self, *args: object, **options: object) -> None:
        """Run until SIGINT or SIGTERM, finishing the current batch first."""
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
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
                "group.id": env.kafka_consumer_group_ingest,
                "enable.auto.commit": False,
                "auto.offset.reset": "earliest",
                "isolation.level": "read_committed",
            }
        )
        ingestor = Ingestor(
            env.kafka_consumer_group_ingest,
            env.kafka_topic_events_dlq,
            producer_for_dead_letters(env.kafka_bootstrap_servers),
            PartitionFilters(env.dedupe_expected_items, env.dedupe_target_fpr),
        )
        run(ingestor, consumer, env.kafka_topic_events_raw, env.ingest_max_batch, lambda: stopping)
