"""Close batches of leaves into signed checkpoints (ADR-0003, ADR-0007).

There is one checkpointer at a time, enforced with a Postgres advisory lock. It
keeps the whole log's leaf hashes in a :class:`LogTree`, extends it from
``ledger_event`` as appends commit, and closes a batch when either
``MERKLE_BATCH_MAX_SIZE`` leaves are waiting or the oldest waiting leaf has
waited ``MERKLE_BATCH_MAX_AGE_MS``.

Before signing, it checks that the log still has the root the previous
checkpoint signed. If someone rewrote stored leaves, the roots disagree and the
checkpointer refuses to sign anything, rather than blessing the rewrite.

Every checkpoint is appended to a local witness file. Once per witness interval
the latest checkpoint is also timestamped externally (see
:mod:`apps.ledger.timestamps`).
"""

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from django.db import connection, transaction

from apps.ledger import timestamps
from apps.ledger.models import Outbox
from tallyproof_core.checkpoint import Checkpoint, Signer, key_id
from tallyproof_core.ids import new_id
from tallyproof_core.log_tree import LogTree

log = logging.getLogger(__name__)

ADVISORY_LOCK_KEY = 0x7A11_9F00
"""Postgres advisory lock held by the one running checkpointer."""


class CheckpointerError(RuntimeError):
    """The log is not in a state the checkpointer may sign."""


@dataclass(frozen=True)
class Signed:
    """One closed batch."""

    public_id: str
    start_index: int
    tree_size: int
    root_hash: bytes
    note: str


@dataclass(frozen=True)
class WitnessPolicy:
    """Where checkpoints are exported and how often they are timestamped externally."""

    export_path: Path
    interval_seconds: int
    calendars: list[str]


def load_signed_head() -> tuple[int, bytes | None]:
    """Size and root of the newest checkpoint, or (0, None) for a fresh log."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tree_size, root_hash FROM ledger_batch ORDER BY tree_size DESC LIMIT 1"
        )
        row = cursor.fetchone()
    return (int(row[0]), bytes(row[1])) if row else (0, None)


def extend(tree: LogTree) -> int:
    """Add committed leaves past the tree's current size. Returns how many were added.

    Leaf indexes and the log head commit together, so committed leaves are
    always a gap-free prefix; a gap here means the table was tampered with.
    """
    added = 0
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT leaf_index, leaf_hash FROM ledger_event"
            " WHERE leaf_index >= %s ORDER BY leaf_index",
            [tree.size],
        )
        for leaf_index, leaf in cursor:
            if leaf_index != tree.size:
                raise CheckpointerError(f"leaf {tree.size} is missing; found {leaf_index} instead")
            tree.append(bytes(leaf))
            added += 1
    return added


class Checkpointer:
    """Decides when to close a batch, signs it, and records it."""

    def __init__(
        self,
        signer: Signer,
        batch_max_size: int,
        batch_max_age_ms: int,
        witness: WitnessPolicy | None = None,
        clock: Callable[[], float] = time.monotonic,
        announce_topic: str | None = None,
    ) -> None:
        """Load the log and the newest checkpoint, and check they agree."""
        self.signer = signer
        self.key_id = key_id(signer.name, signer.public_key).hex()
        self.batch_max_size = batch_max_size
        self.batch_max_age = batch_max_age_ms / 1000
        self.witness = witness
        self.clock = clock
        self.announce_topic = announce_topic
        self.tree = LogTree()
        self.signed_size, self.signed_root = load_signed_head()
        self.waiting_since: float | None = None
        self.last_stamped: float | None = None
        extend(self.tree)
        self._check_signed_prefix()

    def _check_signed_prefix(self) -> None:
        if self.signed_root is None:
            return
        if self.tree.size < self.signed_size:
            raise CheckpointerError(
                f"log has {self.tree.size} leaves but checkpoint {self.signed_size} was signed"
            )
        if self.tree.root(self.signed_size) != self.signed_root:
            raise CheckpointerError(
                f"stored leaves no longer match signed checkpoint {self.signed_size};"
                " refusing to sign"
            )

    @property
    def pending(self) -> int:
        """Leaves appended since the newest checkpoint."""
        return self.tree.size - self.signed_size

    def seconds_until_due(self) -> float | None:
        """How long until the waiting leaves must be closed, or None if none are waiting."""
        if self.waiting_since is None:
            return None
        return max(0.0, self.waiting_since + self.batch_max_age - self.clock())

    def tick(self) -> Signed | None:
        """Pick up new leaves and close a batch if one is due."""
        extend(self.tree)
        if self.pending == 0:
            self.waiting_since = None
            return None
        now = self.clock()
        if self.waiting_since is None:
            self.waiting_since = now
        if self.pending >= self.batch_max_size or now - self.waiting_since >= self.batch_max_age:
            return self.close()
        return None

    def close(self) -> Signed:
        """Sign a checkpoint over the whole log and record the batch.

        Raises:
            CheckpointerError: If no leaves are waiting, or the signed prefix changed.
        """
        extend(self.tree)
        if self.pending == 0:
            raise CheckpointerError("no leaves are waiting to be checkpointed")
        self._check_signed_prefix()
        size = self.tree.size
        root_hash = self.tree.root(size)
        note = self.signer.sign_checkpoint(Checkpoint(self.signer.name, size, root_hash))
        signed = Signed(new_id("bat"), self.signed_size, size, root_hash, note)
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO ledger_batch (public_id, start_index, tree_size, root_hash,"
                " checkpoint_note, key_id) VALUES (%s, %s, %s, %s, %s, %s)",
                [signed.public_id, signed.start_index, size, root_hash, note, self.key_id],
            )
            if self.announce_topic is not None:
                Outbox.objects.create(
                    topic=self.announce_topic,
                    key=self.signer.name,
                    payload={
                        "batch_id": signed.public_id,
                        "start_index": signed.start_index,
                        "tree_size": size,
                        "root_hash_hex": root_hash.hex(),
                    },
                )
        self.signed_size, self.signed_root, self.waiting_since = size, root_hash, None
        if self.witness is not None:
            self._export(signed)
        return signed

    def _export(self, signed: Signed) -> None:
        assert self.witness is not None  # noqa: S101 - only called when configured
        path = self.witness.export_path
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "tree_size": signed.tree_size,
            "root_hash_hex": signed.root_hash.hex(),
            "note": signed.note,
            "exported_at": datetime.now(UTC).isoformat(),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        now = self.clock()
        due = self.last_stamped is None or now - self.last_stamped >= self.witness.interval_seconds
        if self.witness.calendars and due:
            target = path.parent / f"checkpoint-{signed.tree_size}.note"
            result = timestamps.stamp(signed.note.encode(), target, self.witness.calendars)
            if result.written:
                self.last_stamped = now
            for calendar, problem in result.failed.items():
                log.warning("timestamp calendar %s failed: %s", calendar, problem)


def try_lock() -> bool:
    """Take the single-checkpointer lock for this database session."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [ADVISORY_LOCK_KEY])
        return bool(cursor.fetchone()[0])
