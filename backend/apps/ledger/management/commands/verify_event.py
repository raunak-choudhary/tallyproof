"""``python manage.py verify_event``: check an event from a running API, trusting only the key.

This is the browser's check, from a terminal. The API supplies the event's bytes
and a proof; this command recomputes the leaf hash, walks the audit path, and
checks the checkpoint's signature against ``CHECKPOINT_PUBLIC_KEY``. Nothing the
API says is taken as a verdict.
"""

import json
import random

import requests
from django.core.management.base import BaseCommand, CommandError, CommandParser

from config.env import app_settings
from tallyproof_core.checkpoint import CheckpointError, Verifier
from tallyproof_core.hashing import leaf_hash
from tallyproof_core.merkle import verify_inclusion


class Command(BaseCommand):
    """Verify one event against the pinned key."""

    help = "Fetch an event and its proof from the API and verify both locally."

    def add_arguments(self, parser: CommandParser) -> None:
        """Accept the API address and an optional event ID."""
        parser.add_argument("--api", help="API base URL; API_BASE_URL when omitted")
        parser.add_argument("--event", help="event ID; a random recent one if omitted")

    def handle(self, *args: object, **options: object) -> None:
        """Print each check; exit non-zero if any fails."""
        api = str(options["api"] or app_settings().api_base_url).rstrip("/")
        with requests.Session() as http:
            event_id = options["event"]
            if not event_id:
                listed = http.get(f"{api}/api/v1/events?limit=200", timeout=10).json()["results"]
                if not listed:
                    raise CommandError("the ledger has no events yet")
                event_id = random.choice(listed)["event_id"]  # noqa: S311 - picking a sample
            event = http.get(f"{api}/api/v1/events/{event_id}", timeout=10).json()
            proof = http.get(f"{api}/api/v1/events/{event_id}/proof", timeout=10).json()
        if "audit_path_hex" not in proof:
            raise CommandError(f"no proof yet: {proof.get('detail', proof)}")
        # A valid record and proof for some other event would verify too, so the
        # record must name the event that was asked for.
        served = json.loads(event["canonical"]).get("event_id")
        if served != event_id:
            raise CommandError(
                f"record: FAILED (the record served is for {served}, not {event_id})"
            )
        self.stdout.write(f"record: ok (it is {event_id})")

        verifier = Verifier.from_verifier_key(app_settings().checkpoint_public_key)
        try:
            checkpoint = verifier.verify_checkpoint(proof["checkpoint_note"])
        except CheckpointError as error:
            raise CommandError(f"checkpoint signature: FAILED ({error})") from error
        self.stdout.write(
            f"checkpoint signature: ok ({checkpoint.origin}, {checkpoint.tree_size} leaves)"
        )
        leaf = leaf_hash(event["canonical"].encode())
        self.stdout.write(f"leaf hash recomputed: {leaf.hex()}")
        index = proof["leaf_index"]
        path = [bytes.fromhex(node) for node in proof["audit_path_hex"]]
        if not verify_inclusion(leaf, index, checkpoint.tree_size, path, checkpoint.root_hash):
            raise CommandError("inclusion proof: FAILED")
        self.stdout.write(
            f"inclusion proof: ok (leaf {index}, {len(path)} hashes to the signed root)"
        )
        self.stdout.write(self.style.SUCCESS(f"{event_id} verified"))
