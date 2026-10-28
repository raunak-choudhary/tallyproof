"""Find the policy text a question is about: keyword and vector search, fused.

The corpus is the FAR sections in the log, one ``policy.published`` leaf each.
Sections are split into overlapping chunks along paragraph breaks, and every
chunk remembers its leaf and its character offsets, so a quote can be cited to
the exact leaf that holds it and checked against that leaf's text.

Two rankings are combined with reciprocal rank fusion: BM25 over words, which
finds exact terms such as "change order", and cosine similarity over local
embeddings, which finds paraphrases. The embedding model runs on the CPU through
ONNX and is never a hosted service, so no question leaves the machine to be
embedded. Tests use a fake embedder.
"""

import hashlib
import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

CHUNK_CHARS = 1200
OVERLAP_CHARS = 200
BM25_K1 = 1.2
BM25_B = 0.75
RRF_K = 60
TOKEN = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")
STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have", "how", "in",
        "is", "it", "its", "of", "on", "or", "that", "the", "this", "to", "was", "what", "when",
        "where", "which", "who", "will", "with", "does", "do", "say", "says", "about", "under",
    }
)  # fmt: skip


@dataclass(frozen=True)
class PolicyLeaf:
    """One FAR section as it sits in the log."""

    event_id: str
    leaf_index: int
    section: str
    title: str
    text: str


@dataclass(frozen=True)
class Chunk:
    """A piece of one section, with where it starts and ends in that section's text."""

    leaf: PolicyLeaf
    start: int
    end: int

    @property
    def text(self) -> str:
        """The chunk's text, sliced from the leaf so it can't drift from it."""
        return self.leaf.text[self.start : self.end]


@dataclass(frozen=True)
class Hit:
    """A retrieved chunk and its fused score."""

    chunk: Chunk
    score: float


class Embedder(Protocol):
    """Turns texts into vectors of a fixed size."""

    model_id: str

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        """Return one row per text."""
        ...


def chunk(leaf: PolicyLeaf, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[Chunk]:
    """Split a section into chunks of about ``size`` characters, ending on paragraph breaks."""
    text = leaf.text
    chunks: list[Chunk] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind("\n", start + size // 2, end)
            if cut == -1:
                cut = text.rfind(" ", start + size // 2, end)
            end = cut if cut > start else end
        chunks.append(Chunk(leaf, start, end))
        if end == len(text):
            break
        start = max(end - overlap, start + 1)
        while start < len(text) and not text[start - 1].isspace():
            start += 1  # begin on a word boundary
    return chunks


def tokens(text: str) -> list[str]:
    """Lowercase word tokens without stopwords; section numbers stay whole."""
    return [t for t in TOKEN.findall(text.lower()) if t not in STOPWORDS]


class BM25:
    """Okapi BM25 over a fixed set of documents."""

    def __init__(self, documents: Sequence[str]) -> None:
        """Index the documents."""
        self._docs = [Counter(tokens(d)) for d in documents]
        self._lengths = [sum(d.values()) for d in self._docs]
        self._average = (sum(self._lengths) / len(self._lengths)) if self._docs else 0.0
        frequency: Counter[str] = Counter()
        for doc in self._docs:
            frequency.update(doc.keys())
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in frequency.items()}

    def scores(self, query: str) -> list[float]:
        """Score every document against the query."""
        terms = tokens(query)
        out = []
        for doc, length in zip(self._docs, self._lengths, strict=True):
            score = 0.0
            for term in terms:
                tf = doc.get(term, 0)
                if tf:
                    norm = BM25_K1 * (1 - BM25_B + BM25_B * length / (self._average or 1))
                    score += self._idf[term] * tf * (BM25_K1 + 1) / (tf + norm)
            out.append(score)
        return out


def _ranks(scores: Sequence[float]) -> dict[int, int]:
    ordered = sorted((i for i, s in enumerate(scores) if s > 0), key=lambda i: (-scores[i], i))
    return {index: rank for rank, index in enumerate(ordered)}


class PolicyIndex:
    """Hybrid keyword and vector search over policy chunks."""

    def __init__(
        self, leaves: Sequence[PolicyLeaf], embedder: Embedder, cache_dir: Path | None = None
    ) -> None:
        """Chunk and index the leaves; chunk vectors are cached on disk by content hash."""
        self.chunks = [c for leaf in leaves for c in chunk(leaf)]
        self._bm25 = BM25([f"{c.leaf.section} {c.leaf.title} {c.text}" for c in self.chunks])
        self._embedder = embedder
        self._vectors = self._embed_chunks(cache_dir)

    def _embed_chunks(self, cache_dir: Path | None) -> np.ndarray:
        texts = [f"{c.leaf.title}\n{c.text}" for c in self.chunks]
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        digest = hashlib.sha256(
            "\x00".join([self._embedder.model_id, *texts]).encode()
        ).hexdigest()[:24]
        path = cache_dir / f"{digest}.npy" if cache_dir else None
        if path is not None and path.exists():
            loaded: np.ndarray = np.load(path)
            return loaded
        vectors = _normalize(self._embedder.embed(texts))
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            np.save(path, vectors)
        return vectors

    def search(self, query: str, k: int = 5) -> list[Hit]:
        """The ``k`` best chunks by reciprocal rank fusion of BM25 and cosine similarity."""
        if not self.chunks:
            return []
        lexical = _ranks(self._bm25.scores(query))
        query_vector = _normalize(self._embedder.embed([query]))[0]
        similarity = (self._vectors @ query_vector).tolist()
        semantic = _ranks([max(s, 0.0) for s in similarity])
        fused: dict[int, float] = {}
        for ranking in (lexical, semantic):
            for index, rank in ranking.items():
                fused[index] = fused.get(index, 0.0) + 1.0 / (RRF_K + rank + 1)
        best = sorted(fused, key=lambda i: (-fused[i], i))[:k]
        return [Hit(self.chunks[i], fused[i]) for i in best]


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return (vectors / np.where(norms == 0, 1, norms)).astype(np.float32)


class FastEmbedder:
    """Local embeddings with fastembed (ONNX on the CPU). The model downloads once."""

    def __init__(self, model_id: str, cache_dir: Path) -> None:
        """Load the model, downloading it into ``cache_dir`` the first time."""
        from fastembed import TextEmbedding

        self.model_id = model_id
        self._model = TextEmbedding(model_name=model_id, cache_dir=str(cache_dir))

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        """Embed the texts."""
        return np.array(list(self._model.embed(list(texts))), dtype=np.float32)


def load_leaves() -> list[PolicyLeaf]:
    """Every FAR section in the log, in log order."""
    from apps.ledger.models import LedgerEvent

    rows = LedgerEvent.objects.filter(event_type="policy.published").order_by("leaf_index")
    return [
        PolicyLeaf(
            row.public_id,
            row.leaf_index,
            row.payload["section"],
            row.payload["title"],
            row.payload["text"],
        )
        for row in rows.only("public_id", "leaf_index", "payload")
    ]
