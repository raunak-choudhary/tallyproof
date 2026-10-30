"""A process-wide copy of the log's leaf hashes for building proofs quickly.

Each API process keeps one :class:`LogTree` and extends it with newly committed
leaves before answering. Proofs are built only for sizes that a signed
checkpoint covers, so every proof a client receives can be checked against a
signature.
"""

import threading

from apps.ledger.checkpointer import extend
from apps.ledger.totals import build_tree
from tallyproof_core.log_tree import LogTree
from tallyproof_core.sum_tree import SumTree

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
    """Forget every cached leaf and sum tree. For tests, which rebuild the database."""
    global _tree
    with _lock:
        _tree = LogTree()
    with _sums_lock:
        _sums.clear()


_sums: dict[int, SumTree] = {}
_sums_lock = threading.Lock()
SUM_TREES_KEPT = 2


def sum_tree(tree_size: int) -> SumTree:
    """The sum tree of the checkpoint at ``tree_size``, built once per process.

    Only the newest few are kept: on a million records each takes about 500 MB.
    """
    with _sums_lock:
        tree = _sums.get(tree_size)
        if tree is None:
            tree = build_tree(tree_size)
            _sums[tree_size] = tree
            for old in sorted(_sums)[:-SUM_TREES_KEPT]:
                del _sums[old]
        return tree
