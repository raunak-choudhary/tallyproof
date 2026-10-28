from tests.vectors_builder import VECTORS_DIR, build_canonical, render


def test_committed_canonical_vectors_match_the_core_library():
    committed = (VECTORS_DIR / "canonical.json").read_text(encoding="utf-8")
    assert committed == render(build_canonical()), "run `make vectors` and commit the result"
