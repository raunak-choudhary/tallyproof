"""``python manage.py project``: keep the derived views up to date with the log."""

import logging
import signal
from types import FrameType

import psycopg
from django.core.management.base import BaseCommand
from django.db import connection

from apps.ledger.append import APPENDED_CHANNEL
from apps.ledger.projections import AppendedProjection, JournalProjection, Projection, run_round
from apps.reconciliation.projection import ReconciliationProjection
from config.env import app_settings
from config.logging import configure

log = logging.getLogger(__name__)
IDLE_WAIT_SECONDS = 5.0


class Command(BaseCommand):
    """Run the appended, journal, and reconciliation projections."""

    help = "Derive the journal and reconciliation breaks from the log as it grows."

    def handle(self, *args: object, **options: object) -> None:
        """Run until SIGINT or SIGTERM."""
        configure()
        stopping = False

        def stop(signum: int, frame: FrameType | None) -> None:
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        projections: list[Projection] = [
            AppendedProjection(app_settings().kafka_topic_ledger_appended),
            JournalProjection(),
            ReconciliationProjection(),
        ]
        settings = connection.settings_dict
        with psycopg.connect(
            dbname=settings["NAME"],
            user=settings["USER"],
            password=settings["PASSWORD"],
            host=settings["HOST"],
            port=settings["PORT"] or 5432,
            autocommit=True,
        ) as listener:
            listener.execute(f"LISTEN {APPENDED_CHANNEL}")
            while not stopping:
                read = run_round(projections)
                if read:
                    log.info("projected %d events", read)
                    continue
                for _ in listener.notifies(timeout=IDLE_WAIT_SECONDS, stop_after=1):
                    pass
