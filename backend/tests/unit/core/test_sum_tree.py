"""The Merkle-sum tree: honest proofs verify to the right total, and every lie is caught."""

import dataclasses
import hashlib

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tallyproof_core.hashing import EMPTY_ROOT
from tallyproof_core.sum_tree import (
    LeafPiece,
    NodePiece,
    Proven,
    SumLeaf,
    SumTree,
    SumTreeError,
    TotalProof,
    encode_key,
    proof_from_json,
    proof_to_json,
    verify_total,
)

ENTITIES = ("obligations", "outlays")
AGENCIES = ("", "Agency A", "Agency AB", "Agency B")
YEARS = ("", "2024", "2025")


def record_hash(n: int) -> bytes:
    return hashlib.sha256(str(n).encode()).digest()


@st.composite
def leaf_sets(draw: st.DrawFn, max_size: int = 60) -> list[SumLeaf]:
    rows = draw(
        st.lists(
            st.tuples(
                st.sampled_from(ENTITIES),
                st.sampled_from(AGENCIES),
                st.sampled_from(YEARS),
                st.integers(-(10**9), 10**12),
            ),
            min_size=1,
            max_size=max_size,
        )
    )
    return [
        SumLeaf((e, a, y, f"{n:020d}"), amount, record_hash(n))
        for n, (e, a, y, amount) in enumerate(rows)
    ]


prefixes = st.sampled_from(
    [
        (),
        *((e,) for e in ENTITIES),
        *((e, a) for e in ENTITIES for a in AGENCIES),
        *((e, a, y) for e in ENTITIES for a in AGENCIES for y in YEARS),
        ("nothing",),
    ]
)


def expected(leaves: list[SumLeaf], prefix: tuple[str, ...]) -> Proven:
    under = [leaf for leaf in leaves if leaf.key[: len(prefix)] == prefix]
    return Proven(sum(leaf.amount for leaf in under), len(under))


@settings(max_examples=300)
@given(leaves=leaf_sets(), prefix=prefixes)
def test_an_honest_proof_gives_the_exact_total(
    leaves: list[SumLeaf], prefix: tuple[str, ...]
) -> None:
    tree = SumTree(leaves, cache_min=4)
    assert verify_total(tree.prove(prefix), tree.root()) == expected(leaves, prefix)


@given(leaves=leaf_sets())
def test_the_root_does_not_depend_on_input_order(leaves: list[SumLeaf]) -> None:
    assert SumTree(leaves).root() == SumTree(list(reversed(leaves))).root()


@given(leaves=leaf_sets(max_size=200))
def test_caching_never_changes_the_root(leaves: list[SumLeaf]) -> None:
    assert SumTree(leaves, cache_min=1).root() == SumTree(leaves, cache_min=256).root()


@given(leaves=leaf_sets())
def test_the_whole_tree_total_is_the_sum_of_every_leaf(leaves: list[SumLeaf]) -> None:
    assert SumTree(leaves).total() == sum(leaf.amount for leaf in leaves)


def test_a_prefix_is_a_whole_component_not_a_string_prefix() -> None:
    leaves = [
        SumLeaf(("obligations", "Agency A", "2024", "1"), 100, record_hash(1)),
        SumLeaf(("obligations", "Agency AB", "2024", "2"), 7, record_hash(2)),
    ]
    tree = SumTree(leaves)
    assert verify_total(tree.prove(("obligations", "Agency A")), tree.root()) == Proven(100, 1)


def test_the_empty_tree_proves_a_zero_total() -> None:
    tree = SumTree([])
    assert tree.root() == EMPTY_ROOT
    assert verify_total(tree.prove(("obligations",)), EMPTY_ROOT) == Proven(0, 0)


# Lies. Each one must fail verification.


def changed(piece: LeafPiece | NodePiece) -> LeafPiece | NodePiece:
    if isinstance(piece, LeafPiece):
        return LeafPiece(dataclasses.replace(piece.leaf, amount=piece.leaf.amount + 1))
    return dataclasses.replace(piece, total=piece.total + 1)


@given(leaves=leaf_sets(), prefix=prefixes, data=st.data())
def test_changing_any_piece_fails(
    leaves: list[SumLeaf], prefix: tuple[str, ...], data: st.DataObject
) -> None:
    tree = SumTree(leaves)
    proof = tree.prove(prefix)
    i = data.draw(st.integers(0, len(proof.pieces) - 1))
    pieces = list(proof.pieces)
    pieces[i] = changed(pieces[i])
    assert verify_total(dataclasses.replace(proof, pieces=tuple(pieces)), tree.root()) is None


@given(leaves=leaf_sets(), prefix=prefixes)
def test_dropping_or_adding_a_piece_fails(leaves: list[SumLeaf], prefix: tuple[str, ...]) -> None:
    tree = SumTree(leaves)
    proof = tree.prove(prefix)
    assert verify_total(dataclasses.replace(proof, pieces=proof.pieces[:-1]), tree.root()) is None
    extra = (*proof.pieces, proof.pieces[0])
    assert verify_total(dataclasses.replace(proof, pieces=extra), tree.root()) is None


@given(leaves=leaf_sets(), prefix=prefixes)
def test_a_proof_for_another_root_fails(leaves: list[SumLeaf], prefix: tuple[str, ...]) -> None:
    tree = SumTree(leaves)
    other = SumTree([*leaves, SumLeaf(("zzz",), 1, record_hash(-1))])
    assert verify_total(tree.prove(prefix), other.root()) is None


@given(leaves=leaf_sets(), prefix=prefixes.filter(bool))
def test_leaving_out_a_matching_record_at_either_end_fails(
    leaves: list[SumLeaf], prefix: tuple[str, ...]
) -> None:
    tree = SumTree(leaves)
    start, end = tree.run(prefix)
    if start == end:
        return
    # A dishonest server claims the run is one record shorter, hiding a record.
    assert verify_total(tree._prove(prefix, start + 1, end), tree.root()) is None
    assert verify_total(tree._prove(prefix, start, end - 1), tree.root()) is None


@given(leaves=leaf_sets(), prefix=prefixes.filter(bool))
def test_widening_the_run_past_the_prefix_fails(
    leaves: list[SumLeaf], prefix: tuple[str, ...]
) -> None:
    tree = SumTree(leaves)
    start, end = tree.run(prefix)
    if start > 0:
        assert verify_total(tree._prove(prefix, start - 1, end), tree.root()) is None
    if end < tree.size:
        assert verify_total(tree._prove(prefix, start, end + 1), tree.root()) is None


def test_keys_out_of_order_fail() -> None:
    # Build a tree whose leaves are honest but signed in the wrong order.
    a = SumLeaf(("a", "1"), 1, record_hash(1))
    b = SumLeaf(("b", "2"), 2, record_hash(2))
    tree = SumTree([a, b])
    swapped = TotalProof(2, ("a",), 0, 1, (LeafPiece(b), LeafPiece(a)))
    assert verify_total(swapped, tree.root()) is None


def test_malformed_proofs_fail_quietly() -> None:
    tree = SumTree([SumLeaf(("a",), 1, record_hash(1)), SumLeaf(("b",), 2, record_hash(2))])
    proof = tree.prove(("a",))
    assert verify_total(dataclasses.replace(proof, size=-1), tree.root()) is None
    assert verify_total(dataclasses.replace(proof, start=2, end=1), tree.root()) is None
    bad_hash = LeafPiece(SumLeaf(("a",), 1, b"short"))
    assert (
        verify_total(dataclasses.replace(proof, pieces=(bad_hash, proof.pieces[1])), tree.root())
        is None
    )


# Construction rules.


def test_two_leaves_with_one_key_are_refused() -> None:
    with pytest.raises(SumTreeError):
        SumTree([SumLeaf(("a",), 1, record_hash(1)), SumLeaf(("a",), 2, record_hash(2))])


def test_keys_may_not_contain_nul() -> None:
    with pytest.raises(SumTreeError):
        encode_key(("a\x00b",))
    with pytest.raises(SumTreeError):
        encode_key(())


@given(leaves=leaf_sets(), prefix=prefixes)
def test_json_round_trip_keeps_the_proof(leaves: list[SumLeaf], prefix: tuple[str, ...]) -> None:
    proof = SumTree(leaves).prove(prefix)
    assert proof_from_json(proof_to_json(proof)) == proof


def test_malformed_json_is_refused() -> None:
    with pytest.raises(SumTreeError):
        proof_from_json({"size": 1, "pieces": [{"leaf": {}}]})


@given(leaves=leaf_sets(max_size=200), prefix=prefixes)
def test_proofs_stay_small(leaves: list[SumLeaf], prefix: tuple[str, ...]) -> None:
    proof = SumTree(leaves).prove(prefix)
    assert len(proof.pieces) <= 2 * max(1, len(leaves)).bit_length() + 2
