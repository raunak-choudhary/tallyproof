"""``python manage.py tamper``: the tamper demo (local only, owner role).

Run with ``DJANGO_SETTINGS_MODULE=config.settings.migrate`` and
``DEMO_TAMPER_ENABLED=true``. ``--restore`` undoes the last run.
"""

import json
import os

import psycopg
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import connection

from apps.ledger import tamper
from config.env import REPO_ROOT, checkpointer_settings
from tallyproof_core.checkpoint import Signer, decode_private_key

BACKUP = REPO_ROOT / "var" / "demo" / "tamper-backup.json"


class Command(BaseCommand):
    """Tamper at one level of the ladder, or undo it."""

    help = "Tamper with the local ledger at level 1, 2, or 3, or restore it."

    def add_arguments(self, parser: CommandParser) -> None:
        """Level and target, or --restore."""
        parser.add_argument("--level", type=int, choices=[1, 2, 3, 4])
        parser.add_argument("--event", help="event ID to edit")
        parser.add_argument("--amount", default="999999.00", help="the forged amount")
        parser.add_argument("--restore", action="store_true", help="undo the last tamper run")

    def handle(self, *args: object, **options: object) -> None:
        """Check the guards, then tamper or restore."""
        settings = connection.settings_dict
        try:
            tamper.check_safe(os.environ.get("DEMO_TAMPER_ENABLED") == "true", settings["HOST"])
        except tamper.TamperRefusedError as error:
            raise CommandError(str(error)) from error
        with psycopg.connect(
            dbname=settings["NAME"],
            user=settings["USER"],
            password=settings["PASSWORD"],
            host=settings["HOST"],
            port=settings["PORT"] or 5432,
        ) as conn:
            if options["restore"]:
                tamper.restore(conn, json.loads(BACKUP.read_text(encoding="utf-8")))
                BACKUP.unlink()
                self.stdout.write("restored the ledger from the tamper backup")
                return
            level = options["level"]
            if not isinstance(level, int):
                raise CommandError("give --level 1, 2, or 3 and --event")
            if level == 4:
                raise CommandError(
                    "level 4 happens inside the witness interval and is not detectable; "
                    "docs/architecture.md explains it rather than demonstrating it"
                )
            if not options["event"]:
                raise CommandError("give --level 1, 2, or 3 and --event")
            if BACKUP.exists():
                raise CommandError("a tamper run is still in place; run with --restore first")
            backup = {
                "event": tamper.edit_event(conn, str(options["event"]), str(options["amount"]))
            }
            if level >= 2:
                signer = None
                if level == 3:
                    env = checkpointer_settings()
                    key = decode_private_key(env.checkpoint_signing_key_file.read_text())
                    signer = Signer(env.merkle_log_origin, key)
                backup["checkpoint"] = tamper.rebuild_checkpoint(conn, signer)
            BACKUP.parent.mkdir(parents=True, exist_ok=True)
            BACKUP.write_text(json.dumps(backup), encoding="utf-8")
        self.stdout.write(
            f"level {level} applied; check it with make verify-event / verify-witness"
        )
