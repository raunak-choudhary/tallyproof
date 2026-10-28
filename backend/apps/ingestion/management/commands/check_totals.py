"""``python manage.py check_totals``: re-read the raw topic and check the ledger accounts for it."""

from confluent_kafka import Consumer, TopicPartition
from django.core.management.base import BaseCommand, CommandError

from apps.ingestion.control_totals import reconcile_range
from apps.ingestion.offsets import stored
from config.env import app_settings


class Command(BaseCommand):
    """Control totals per partition, up to each partition's committed offset."""

    help = "Check that every consumed message was appended, refused, or dead-lettered."

    def handle(self, *args: object, **options: object) -> None:
        """Print one line per partition; exit non-zero on any mismatch."""
        env = app_settings()
        topic, group = env.kafka_topic_events_raw, env.kafka_consumer_group_ingest
        consumer = Consumer(
            {
                "bootstrap.servers": env.kafka_bootstrap_servers,
                "group.id": "control-totals",
                "enable.auto.commit": False,
            }
        )
        partitions = consumer.list_topics(topic, timeout=10).topics[topic].partitions
        failures = 0
        for partition in sorted(partitions):
            end = stored(group, topic, partition)
            consumer.assign([TopicPartition(topic, partition, 0)])
            messages: dict[int, bytes | None] = {}
            while len(messages) < end:
                batch = consumer.consume(num_messages=1000, timeout=5.0)
                if not batch:
                    break
                for m in batch:
                    offset = m.offset()
                    if m.error() is None and offset is not None and offset < end:
                        messages[offset] = m.value()
            report = reconcile_range(topic, partition, messages, 0, end)
            failures += not report.ok
            self.stdout.write(
                f"partition {partition}: {report.messages} messages = {report.appended} appended"
                f" + {report.duplicates} duplicates + {report.invalid} invalid;"
                f" amounts {'match' if report.stream_amount == report.ledger_amount else 'DIFFER'}"
            )
            for problem in report.problems[:20]:
                self.stderr.write(f"  {problem}")
        consumer.close()
        if failures:
            raise CommandError(f"{failures} partitions failed their control totals")
