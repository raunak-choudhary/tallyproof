"""Build and sign the Merkle-sum tree of a checkpoint (ADR-0024).

The tree is a pure function of the records in one checkpoint, so it is rebuilt
from the ledger rather than kept up to date: a record's agency can change when its
award's first record arrives late. The checkpointer, the only process holding the
signing key, signs it right after a checkpoint, at every checkpoint while the log
is small and at most every ``TOTALS_INTERVAL_SECONDS`` after that.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from django.db import connection

from tallyproof_core.checkpoint import Signer, TotalsNote
from tallyproof_core.sum_tree import SumTree
from tallyproof_core.totals import leaves, records_from_canonical

log = logging.getLogger(__name__)

_RECORDS = """
SELECT leaf_index, canonical_bytes, leaf_hash FROM ledger_event
WHERE leaf_index < %s
  AND event_type IN ('obligation.recorded', 'obligation.adjusted', 'outlay.reported')
ORDER BY leaf_index
"""


def build_tree(tree_size: int) -> SumTree:
    """The sum tree of the obligations and outlays in the first ``tree_size`` leaves."""
    with connection.cursor() as cursor:
        cursor.execute(_RECORDS, [tree_size])
        rows = [(int(i), bytes(c), bytes(h)) for i, c, h in cursor.fetchall()]
    return SumTree(leaves(records_from_canonical(rows)))


@dataclass(frozen=True)
class SignedTotals:
    """One signed sum tree."""

    tree_size: int
    root_hash: bytes
    note: str
    records: int


class TotalsSigner:
    """Decides when a checkpoint's totals are due, then builds, signs, and stores them."""

    def __init__(
        self,
        signer: Signer,
        every_checkpoint_up_to: int,
        interval_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Pick up where the newest stored totals left off."""
        self.signer = signer
        self.every_checkpoint_up_to = every_checkpoint_up_to
        self.interval = interval_seconds
        self.clock = clock
        self.last_signed_at: float | None = None
        with connection.cursor() as cursor:
            cursor.execute("SELECT max(tree_size) FROM ledger_totals")
            row = cursor.fetchone()
        self.signed_size = int(row[0]) if row and row[0] is not None else 0

    def due(self, tree_size: int) -> bool:
        """Whether a checkpoint at ``tree_size`` should get its totals signed now."""
        if tree_size <= self.signed_size:
            return False
        if tree_size <= self.every_checkpoint_up_to or self.last_signed_at is None:
            return True
        return self.clock() - self.last_signed_at >= self.interval

    def maybe_sign(self, tree_size: int) -> SignedTotals | None:
        """Sign the totals for the checkpoint at ``tree_size`` if they are due."""
        return self.sign(tree_size) if self.due(tree_size) else None

    def sign(self, tree_size: int) -> SignedTotals:
        """Build, sign, and store the totals of the checkpoint at ``tree_size``."""
        started = time.monotonic()
        tree = build_tree(tree_size)
        root_hash = tree.root()
        note = self.signer.sign_totals(TotalsNote(self.signer.name, tree_size, root_hash))
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO ledger_totals (tree_size, root_hash, totals_note, records)"
                " VALUES (%s, %s, %s, %s)",
                [tree_size, root_hash, note, tree.size],
            )
        self.signed_size, self.last_signed_at = tree_size, self.clock()
        log.info(
            "signed totals for checkpoint %d: %d records in %.1f s",
            tree_size,
            tree.size,
            time.monotonic() - started,
        )
        return SignedTotals(tree_size, root_hash, note, tree.size)
