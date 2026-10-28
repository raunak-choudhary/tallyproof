"""``python manage.py dead_letters``: inspect dead-lettered records and replay fixed ones.

``--list`` prints why each record was rejected. ``--export FILE`` writes the
original records, one per line, for fixing. ``--replay FILE`` validates every
line of a fixed file and, only if all of them pass, publishes them to the raw
topic. Replaying is safe to repeat: the ledger refuses any idempotency key it
already has.
"""

import json
from pathlib import Path

from confluent_kafka import Consumer, Producer
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.ingestion.dead_letter import original, validate_fixed
from config.env import app_settings


class Command(BaseCommand):
    """Inspect and replay the dead-letter topic."""

    help = "List or export dead-lettered records, or replay a file of fixed ones."

    def add_arguments(self, parser: CommandParser) -> None:
        """One of --list, --export, or --replay."""
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--list", action="store_true", help="print each rejection")
        group.add_argument("--export", type=Path, help="write original records to this file")
        group.add_argument("--replay", type=Path, help="publish fixed records from this file")

    def _read_all(self) -> list[bytes]:
        env = app_settings()
        consumer = Consumer(
            {
                "bootstrap.servers": env.kafka_bootstrap_servers,
                "group.id": "dead-letter-inspector",
                "enable.auto.commit": False,
                "auto.offset.reset": "earliest",
            }
        )
        consumer.subscribe([env.kafka_topic_events_dlq])
        records: list[bytes] = []
        while batch := consumer.consume(num_messages=500, timeout=5.0):
            records += [m.value() or b"" for m in batch if m.error() is None]
        consumer.close()
        return records

    def handle(self, *args: object, **options: object) -> None:
        """Run the chosen action."""
        env = app_settings()
        if options["list"] or options["export"]:
            records = self._read_all()
            if options["list"]:
                for record in records:
                    body = json.loads(record)
                    where = body["source"]
                    problems = "; ".join(f"{p['field']}: {p['problem']}" for p in body["problems"])
                    self.stdout.write(f"{where['partition']}:{where['offset']}  {problems}")
                self.stdout.write(f"{len(records)} dead-lettered records")
                return
            path = Path(str(options["export"]))
            path.write_bytes(b"".join(original(r).rstrip(b"\n") + b"\n" for r in records))
            self.stdout.write(f"wrote {len(records)} records to {path}")
            return
        lines = Path(str(options["replay"])).read_text(encoding="utf-8").splitlines()
        lines = [line for line in lines if line.strip()]
        bad = validate_fixed(lines)
        if bad:
            for number, issues in bad:
                self.stderr.write(f"line {number}: {issues}")
            raise CommandError(f"{len(bad)} records still fail validation; nothing was replayed")
        producer = Producer({"bootstrap.servers": env.kafka_bootstrap_servers, "acks": "all"})
        for line in lines:
            producer.produce(env.kafka_topic_events_raw, value=line.encode())
        if producer.flush(30) > 0:
            raise CommandError("the broker did not confirm every replayed record")
        self.stdout.write(f"replayed {len(lines)} fixed records")
