"""Question sets for evaluation, loaded from TOML files in this folder."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
HELD_OUT = HERE / "held_out.toml"

CATEGORIES = frozenset(
    {"numeric_aggregate", "lookup", "anomaly_list", "policy", "refusal", "injection"}
)


@dataclass(frozen=True)
class Question:
    """One question and what the oracle should compute for it."""

    id: str
    text: str
    category: str
    expect: dict[str, Any]
    verified: dict[str, Any] | None = None
    must_not_say: tuple[str, ...] = field(default=())

    @property
    def answerable(self) -> bool:
        """Whether a correct response is an answer rather than a refusal."""
        return bool(self.expect["kind"] != "refuse")


def load(path: Path) -> list[Question]:
    """Read a question file, rejecting unknown categories and duplicate IDs."""
    with path.open("rb") as handle:
        rows = tomllib.load(handle)["question"]
    questions = [
        Question(
            id=row["id"],
            text=row["text"],
            category=row["category"],
            expect=row["expect"],
            verified=row.get("verified"),
            must_not_say=tuple(row.get("must_not_say", ())),
        )
        for row in rows
    ]
    ids = [q.id for q in questions]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate question IDs in {path.name}")
    unknown = {q.category for q in questions} - CATEGORIES
    if unknown:
        raise ValueError(f"unknown categories in {path.name}: {sorted(unknown)}")
    return questions
