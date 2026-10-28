"""Django app configuration for reconciliation."""

from django.apps import AppConfig


class ReconciliationConfig(AppConfig):
    """Matching rules that find breaks between related ledger events."""

    name = "apps.reconciliation"
