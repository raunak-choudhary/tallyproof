"""``python manage.py check_derived``: recompute the journal and compare with what is stored."""

from django.core.management.base import BaseCommand, CommandError

from apps.ledger.derived import journal_drift


class Command(BaseCommand):
    """Detect drift between the stored journal and a fresh derivation."""

    help = "Recompute the journal from the ledger and report any stored entry that differs."

    def handle(self, *args: object, **options: object) -> None:
        """Exit non-zero if any entry differs."""
        problems = journal_drift()
        for problem in problems:
            self.stderr.write(problem)
        if problems:
            raise CommandError("the stored journal differs from the ledger; see rebuild_derived")
        self.stdout.write("the stored journal matches a fresh derivation from the ledger")
