from collections.abc import Sequence
from itertools import pairwise

import numpy as np

from apps.analyst.retrieval import BM25, PolicyIndex, PolicyLeaf, chunk, tokens

VOCABULARY = [
    "change",
    "order",
    "contracting",
    "officer",
    "payment",
    "advance",
    "records",
    "retain",
]


class WordEmbedder:
    """Bag of words over a tiny vocabulary: enough to test fusion without a model."""

    model_id = "fake-words"

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        self.calls += 1
        return np.array([[t.lower().count(w) for w in VOCABULARY] for t in texts], dtype=np.float32)


def leaf(section: str, title: str, text: str, index: int = 0) -> PolicyLeaf:
    return PolicyLeaf(f"evt_{section}", index, section, title, text)


LEAVES = [
    leaf(
        "43.202",
        "Authority to issue change orders.",
        "Only contracting officers may issue a change order.",
        1,
    ),
    leaf(
        "32.402",
        "General.",
        "Advance payments may be authorized when other financing is unavailable.",
        2,
    ),
    leaf(
        "4.705-1",
        "Financial and cost accounting records.",
        "Retain accounting records for 4 years after final payment.",
        3,
    ),
]


def test_chunks_cover_the_text_overlap_and_end_on_breaks():
    paragraphs = "\n".join(f"Paragraph {i} " + "word " * 60 for i in range(12))
    pieces = chunk(leaf("2.101", "Definitions.", paragraphs), size=500, overlap=100)
    assert pieces[0].start == 0
    assert pieces[-1].end == len(paragraphs)
    for before, after in pairwise(pieces):
        assert after.start < before.end  # overlap
        assert before.end - before.start <= 500
        assert paragraphs[before.end] in "\n "
    assert all(p.text == paragraphs[p.start : p.end] for p in pieces)


def test_a_short_section_is_one_chunk():
    (only,) = chunk(LEAVES[0])
    assert only.text == LEAVES[0].text


def test_tokens_keep_section_numbers_and_drop_stopwords():
    assert tokens("What does 4.705-1 say about the records?") == ["4.705-1", "records"]


def test_bm25_prefers_documents_with_rare_matching_terms():
    scores = BM25(["change order authority", "advance payment", "payment records"]).scores(
        "who may issue a change order"
    )
    assert scores[0] > 0
    assert scores[1:] == [0.0, 0.0]


def test_hybrid_search_finds_the_right_section_and_cites_its_leaf(tmp_path):
    embedder = WordEmbedder()
    index = PolicyIndex(LEAVES, embedder, cache_dir=tmp_path)
    (top, *_) = index.search("Who is allowed to issue a change order?", k=2)
    assert top.chunk.leaf.section == "43.202"
    assert top.chunk.leaf.event_id == "evt_43.202"
    assert index.search("how long to retain accounting records")[0].chunk.leaf.section == "4.705-1"
    # Chunk vectors come from the cache the second time.
    calls = embedder.calls
    PolicyIndex(LEAVES, embedder, cache_dir=tmp_path)
    assert embedder.calls == calls
    assert list(tmp_path.glob("*.npy"))


def test_an_empty_corpus_finds_nothing():
    assert PolicyIndex([], WordEmbedder()).search("anything") == []
