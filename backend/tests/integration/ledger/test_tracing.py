"""Signing a checkpoint is one span, with the checkpoint's size."""

import pytest

from apps.ledger.checkpointer import Checkpointer
from tests.fakes import FrozenClock
from tests.integration.conftest import Database
from tests.integration.ledger.test_checkpointer import add_events
from tests.unit.pipeline.test_replay_bundle import SIGNER
from tests.unit.test_tracing import _exporter, provider  # noqa: F401 - installs the exporter

pytestmark = pytest.mark.django_db


def test_closing_a_checkpoint_is_traced(migrated: Database, provider: None) -> None:  # noqa: F811
    _exporter.clear()
    add_events(migrated, 3)
    Checkpointer(SIGNER, 2, 60_000, clock=FrozenClock()).close()
    (span,) = [s for s in _exporter.get_finished_spans() if s.name == "checkpoint.close"]
    assert dict(span.attributes or {})["tallyproof.tree_size"] == 3
