"""A process-wide copy of the log's leaf hashes for building proofs quickly.

Each API process keeps one :class:`LogTree` and extends it with newly committed
leaves before answering. Proofs are built only for sizes that a signed
checkpoint covers, so every proof a client receives can be checked against a
signature.
"""

import threading

from apps.ledger.checkpointer import extend
from tallyproof_core.log_tree import LogTree

_tree = LogTree()
_lock = threading.Lock()


def tree_covering(size: int) -> LogTree:
    """Return the shared tree, extended until it has at least ``size`` leaves."""
    with _lock:
        if _tree.size < size:
            extend(_tree)
        if _tree.size < size:
            raise LookupError(f"the log has {_tree.size} leaves, fewer than {size}")
        return _tree


def reset() -> None:
    """Forget every cached leaf. For tests, which rebuild the database between runs."""
    global _tree
    with _lock:
        _tree = LogTree()
