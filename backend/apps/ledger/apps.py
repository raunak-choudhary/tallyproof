"""Django app configuration for the ledger."""

from django.apps import AppConfig


class LedgerConfig(AppConfig):
    """The append-only event store, Merkle log state, and checkpoints."""

    name = "apps.ledger"
