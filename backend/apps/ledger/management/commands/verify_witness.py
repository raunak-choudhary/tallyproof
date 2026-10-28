"""``python manage.py verify_witness``: check exported checkpoints against the log."""

from django.core.management.base import BaseCommand, CommandError

from apps.ledger.checkpointer import extend
from apps.ledger.witness import verify
from config.env import checkpointer_settings
from tallyproof_core.checkpoint import Verifier
from tallyproof_core.log_tree import LogTree


class Command(BaseCommand):
    """Verify the witness export."""

    help = "Check every exported checkpoint's signature and that the log still matches it."

    def handle(self, *args: object, **options: object) -> None:
        """Print a summary; exit non-zero on any problem."""
        env = checkpointer_settings()
        tree = LogTree()
        extend(tree)
        report = verify(
            env.witness_export_path, Verifier.from_verifier_key(env.checkpoint_public_key), tree
        )
        for problem in report.problems:
            self.stderr.write(problem)
        if not report.ok:
            raise CommandError(f"{len(report.problems)} problems in the witness export")
        self.stdout.write(
            f"{report.checked} checkpoints verified against {tree.size} leaves; "
            f"{report.timestamped} have external timestamps"
            " (check them with `ots verify -f <note> <proof>`)"
        )
