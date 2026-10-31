"""Answers to a fixed list of questions, for the analyst page on the static site.

The static site has no backend, so its analyst page can't ask anything new. This
asks a short list of questions once, live, against a ledger built from exactly the
replay bundle's records, in the bundle's order. That ledger's root at the bundle's
size must equal the bundle's signed root, or nothing is written: then every record
an answer cites sits at the same leaf, under the same signed checkpoint, as in the
bundle, and the browser verifies each citation from the bundle alone.

The answers are written as the API would serve them, to
``frontend/public/replay/answers.json``. They aren't part of the signed bundle; what
makes them checkable is that every citation is.

Usage::

    python -m evals.demo_answers        # make replay-answers (needs Colima and a model key)
"""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tallyproof_core.events import EventEnvelope
from tallyproof_pipeline.settings import REPO_ROOT

BUNDLE = REPO_ROOT / "frontend" / "public" / "replay"
OUT = BUNDLE / "answers.json"
QUESTIONS = (
    "How much did the Department of Veterans Affairs obligate?",
    "How many new awards did the Department of Defense make?",
    "Which agency obligated the most?",
    "Break down total obligations by awarding agency.",
    "What was the largest obligation the Department of Defense recorded?",
    "Show the five largest obligations in the ledger.",
    "Which agency awarded contract 36C26025F0010, and for how much?",
    "Which contracts look like they were recorded twice?",
    "How much will the Department of Veterans Affairs spend next year?",
    "Who is the CEO of the company behind the largest award?",
)


class BundleMismatchError(RuntimeError):
    """The ledger built from the bundle doesn't reproduce the bundle's signed root."""


def bundle_records(bundle: Path = BUNDLE) -> list[dict[str, Any]]:
    """The bundle's records in leaf order, checked to be numbered 0, 1, 2, ..."""
    lines = (bundle / "events.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines if line]
    for position, record in enumerate(records):
        if record["leaf_index"] != position:
            raise BundleMismatchError(f"record {position} sits at leaf {record['leaf_index']}")
    return records


def envelope(record: dict[str, Any]) -> EventEnvelope:
    """The event behind a bundle record.

    A leaf leaves out tracing fields, which aren't hashed, so the correlation ID is a
    fixed one; the root check catches anything else.
    """
    return EventEnvelope.model_validate(
        {**json.loads(record["canonical"]), "correlation_id": "cor_demo_answers"}
    )


def check_citations(answers: list[dict[str, Any]], records: list[dict[str, Any]]) -> None:
    """Every cited record is in the bundle at the leaf the answer says, at its size."""
    leaf_of = {r["event_id"]: r["leaf_index"] for r in records}
    for answer in answers:
        if answer["checkpoint_tree_size"] != len(records):
            raise BundleMismatchError(
                f"{answer['question']!r} is pinned to {answer['checkpoint_tree_size']}, "
                f"not the bundle's {len(records)}"
            )
        cited = [e for c in answer["citations"] for e in c["events"]]
        cited += [
            {"event_id": q["event_id"], "leaf_index": q["leaf_index"]} for q in answer["quotes"]
        ]
        for event in cited:
            if leaf_of.get(event["event_id"]) != event["leaf_index"]:
                raise BundleMismatchError(
                    f"{answer['question']!r} cites {event['event_id']} at leaf "
                    f"{event['leaf_index']}, which the bundle doesn't have"
                )


def _commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 - git from PATH, as make does
        capture_output=True, text=True, check=True, cwd=REPO_ROOT,
    ).stdout.strip()  # fmt: skip


def build_and_ask(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Load the records into a throwaway ledger, check its root, and ask every question."""
    from evals import harness

    with harness.database():
        from django.db import transaction

        from apps.analyst.api import AnswerSerializer
        from apps.analyst.llm import client_for
        from apps.analyst.service import answer_question, models
        from apps.ledger.append import Delivery, append
        from apps.ledger.checkpointer import Checkpointer
        from apps.ledger.models import LedgerBatch
        from apps.ledger.projections import JournalProjection, catch_up
        from apps.reconciliation.projection import ReconciliationProjection
        from config.env import llm_settings

        events = [envelope(r) for r in records]
        with transaction.atomic():
            append([Delivery(e, "demo", 0, i) for i, e in enumerate(events)])
        catch_up(JournalProjection())
        catch_up(ReconciliationProjection())
        Checkpointer(harness.SIGNER, batch_max_size=10**9, batch_max_age_ms=1).close()
        manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
        batch = LedgerBatch.objects.order_by("-tree_size").first()
        if (
            batch is None
            or batch.tree_size != manifest["tree_size"]
            or bytes(batch.root_hash).hex() != manifest["root_hash_hex"]
        ):
            raise BundleMismatchError("the ledger's root differs from the bundle's signed root")
        chosen = models()
        client = client_for("live", llm_settings())
        answers = [
            dict(AnswerSerializer(answer_question(q, client=client, chosen=chosen)).data)
            for q in QUESTIONS
        ]
        return {
            "tree_size": manifest["tree_size"],
            "root_hash_hex": manifest["root_hash_hex"],
            "router_model": chosen.router,
            "answer_model": chosen.answer,
            "computed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "commit": _commit(),
            "answers": answers,
        }


def main() -> None:  # pragma: no cover - needs Docker and a model key
    """Compute the answers, check every citation against the bundle, and write them."""
    records = bundle_records()
    result = build_and_ask(records)
    check_citations(result["answers"], records)
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for answer in result["answers"]:
        print(f"{answer['status']:9} {answer['question']}")
    print(f"wrote {OUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":  # pragma: no cover
    main()
