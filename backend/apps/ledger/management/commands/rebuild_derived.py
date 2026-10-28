"""``python manage.py rebuild_derived journal|reconciliation``: recompute a derived view.

Clears the view and resets its cursor in one transaction; the ``project``
worker then derives it again from the ledger. Needs the owner role, so run it
with ``DJANGO_SETTINGS_MODULE=config.settings.migrate``.
"""

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from apps.ledger.derived import VIEWS, rebuild


class Command(BaseCommand):
    """Clear a derived view for the projections to rebuild."""

    help = "Clear the journal or reconciliation breaks so the project worker rebuilds them."

    def add_arguments(self, parser: CommandParser) -> None:
        """Which view to rebuild."""
        parser.add_argument("view", choices=sorted(VIEWS))

    def handle(self, *args: object, **options: object) -> None:
        """Clear the view."""
        try:
            with transaction.atomic():
                rebuild(str(options["view"]))
        except PermissionError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(f"{options['view']} cleared; the project worker will rebuild it")
