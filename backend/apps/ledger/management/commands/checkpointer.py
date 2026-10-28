"""``python manage.py checkpointer``: sign checkpoints as the log grows."""

import logging
import signal
from types import FrameType

import psycopg
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.ledger.append import APPENDED_CHANNEL
from apps.ledger.checkpointer import Checkpointer, WitnessPolicy, try_lock
from config.env import checkpointer_settings
from config.logging import configure
from tallyproof_core.checkpoint import Signer, decode_private_key

log = logging.getLogger(__name__)
IDLE_WAIT_SECONDS = 5.0


class Command(BaseCommand):
    """Run the single checkpointer."""

    help = "Close batches into signed checkpoints and export them for witnessing."

    def handle(self, *args: object, **options: object) -> None:
        """Run until SIGINT or SIGTERM."""
        configure()
        env = checkpointer_settings()
        key_text = env.checkpoint_signing_key_file.read_text(encoding="utf-8")
        signer = Signer(env.merkle_log_origin, decode_private_key(key_text))
        if signer.verifier_key() != env.checkpoint_public_key:
            raise CommandError("the signing key does not match CHECKPOINT_PUBLIC_KEY")
        if not try_lock():
            raise CommandError("another checkpointer is running")

        stopping = False

        def stop(signum: int, frame: FrameType | None) -> None:
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)

        witness = WitnessPolicy(
            env.witness_export_path,
            env.witness_interval_seconds,
            env.ots_calendar_list if env.witness_ots_enabled else [],
        )
        checkpointer = Checkpointer(
            signer,
            env.merkle_batch_max_size,
            env.merkle_batch_max_age_ms,
            witness,
            announce_topic=env.kafka_topic_checkpoints,
        )
        log.info(
            "checkpointer started at %d leaves, %d signed",
            checkpointer.tree.size,
            checkpointer.signed_size,
        )

        # A second connection only for LISTEN, so waiting never holds a transaction open.
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
                signed = checkpointer.tick()
                if signed is not None:
                    log.info("signed checkpoint %d (%s)", signed.tree_size, signed.public_id)
                    continue
                due = checkpointer.seconds_until_due()
                wait = IDLE_WAIT_SECONDS if due is None else max(due, 0.01)
                # Wake on the next append notification, or when the waiting batch is due.
                for _ in listener.notifies(timeout=wait, stop_after=1):
                    pass
