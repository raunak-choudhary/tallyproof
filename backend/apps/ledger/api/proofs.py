"""A process-wide copy of the log's leaf hashes for building proofs quickly.

Each API process keeps one :class:`LogTree` and extends it with newly committed
leaves before answering. Proofs are built only for sizes that a signed
checkpoint covers, so every proof a client receives can be checked against a
signature.
"""

import threading
from collections import OrderedDict

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


_sums: OrderedDict[int, SumTree] = OrderedDict()
_sums_lock = threading.Lock()
_building = threading.Lock()
SUM_TREES_KEPT = 2


class BuildBusyError(Exception):
    """Another request is building a sum tree; this one should retry shortly."""


def sum_tree(tree_size: int) -> SumTree:
    """The sum tree of the checkpoint at ``tree_size``, built once per process.

    On a million records a tree takes about 500 MB and a few seconds to build, so
    only the most recently used few are kept, and only one is built at a time: a
    request that would start a second build gets :class:`BuildBusyError` instead
    of queueing, so asking for many old checkpoints can't pile up work.
    """
    with _sums_lock:
        tree = _sums.get(tree_size)
        if tree is not None:
            _sums.move_to_end(tree_size)
            return tree
    if not _building.acquire(blocking=False):
        raise BuildBusyError(f"a sum tree is being built; checkpoint {tree_size} must wait")
    try:
        tree = build_tree(tree_size)
    finally:
        _building.release()
    with _sums_lock:
        _sums[tree_size] = tree
        _sums.move_to_end(tree_size)
        while len(_sums) > SUM_TREES_KEPT:
            _sums.popitem(last=False)
    return tree
