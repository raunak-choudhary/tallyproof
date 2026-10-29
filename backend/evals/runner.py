"""Run an evaluation: build a throwaway ledger, ask every question, score, and report.

Usage::

    python -m evals.runner --set smoke --mode cached

``--mode fake`` answers from a script and tests the harness only. ``cached``
replays recorded model responses; any question with a missing recording falls
back to the script, and the whole run is then labeled a harness check. ``live``
calls the configured provider within the run budget and records every response.
Only real runs (live, or cached with nothing missing) are held to the quality
thresholds; integrity is held in every mode.
"""

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from evals import harness
from evals.golden import FULL, SMOKE
from evals.oracle import Oracle
from evals.questions import HELD_OUT, Question, load
from evals.scoring import Observed, Result, as_dict, gate, metrics, score
from tallyproof_pipeline.settings import REPO_ROOT

if TYPE_CHECKING:
    from apps.analyst.pipeline import Models

SETS = {"smoke": [SMOKE], "full": [FULL], "held_out": [HELD_OUT], "all": [FULL, HELD_OUT]}
OUT = REPO_ROOT / "var" / "eval"
RECONCILED = {
    "deobligation_exceeds_award": "deobligation_exceeds_award",
    "duplicate_award_semantic": "possible_duplicate_award",
    "late_arrival": "late_after_close",
    "orphan_outlay": "orphan_outlay",
    "outlay_exceeds_obligation": "outlay_exceeds_obligation",
}
"""Which reconciliation break each labeled anomaly should produce, restated here."""


def fake_script(request: Any) -> str:  # noqa: ANN401 - an LLMRequest; typed loosely to stay import-free
    """Scripted replies that exercise every path without pretending to be good."""
    if request.prompt_version.startswith("router"):
        return json.dumps({"category": "refusal", "refusal_reason": "no_data"})
    if request.prompt_version.startswith("fallback"):
        return json.dumps({"sql": "SELECT 1"})
    return json.dumps({"answer": "The cited records answer this [[c1]]."})


@dataclass
class Meter:
    """Counts tokens and time spent in the model, and cache misses on replay."""

    inner: Any
    fallback: Any = None
    tokens: int = 0
    model_ms: int = 0
    misses: int = 0

    def complete(self, request: Any) -> Any:  # noqa: ANN401
        """Pass the request on, replaying from the fallback on a cache miss."""
        from apps.analyst.llm import CacheMissError

        started = time.monotonic()
        try:
            response = self.inner.complete(request)
        except CacheMissError:
            if self.fallback is None:
                raise
            self.misses += 1
            response = self.fallback.complete(request)
        self.model_ms += int((time.monotonic() - started) * 1000)
        self.tokens += response.input_tokens + response.output_tokens
        return response


def _client(mode: str) -> tuple[Meter, "Models"]:
    from apps.analyst.llm import CachingClient, FakeClient, client_for
    from apps.analyst.pipeline import Models
    from config.env import app_settings, llm_settings

    settings = llm_settings()
    max_rows = app_settings().db_analyst_max_rows
    fake = FakeClient(fake_script)
    manifest = settings.llm_cache_dir / "manifest.json"
    if mode == "fake":
        return Meter(fake), Models(
            "fake-router", "fake-answer", settings.llm_max_output_tokens, max_rows
        )
    if mode == "cached":
        recorded = json.loads(manifest.read_text()) if manifest.exists() else {}
        chosen = Models(
            recorded.get("router_model", "none"),
            recorded.get("answer_model", "none"),
            int(recorded.get("max_output_tokens", settings.llm_max_output_tokens)),
            max_rows,
            recorded.get("reasoning_effort"),
        )
        return Meter(CachingClient(settings.llm_cache_dir), fallback=fake), chosen
    chosen = Models(
        settings.router_model or "none",
        settings.llm_answer_model or "none",
        settings.llm_max_output_tokens,
        max_rows,
        settings.llm_reasoning_effort,
    )
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "router_model": chosen.router,
                "answer_model": chosen.answer,
                "max_output_tokens": chosen.max_output_tokens,
                "reasoning_effort": chosen.reasoning_effort,
            },
            indent=2,
        )
        + "\n"
    )
    return Meter(client_for("live", settings)), chosen


class Integrity:
    """Checks every cited event against the signed checkpoint, the way a browser would."""

    def __init__(self, built: harness.Built) -> None:
        """Load the log and the checkpoint's root."""
        from apps.ledger.checkpointer import extend
        from tallyproof_core.log_tree import LogTree

        self.tree = LogTree()
        extend(self.tree)
        self.checkpoint = built.verifier.verify_checkpoint(built.checkpoint_note)

    def events(self, event_ids: set[str]) -> bool:
        """Every event's bytes hash to its leaf, and its leaf proves into the root."""
        from apps.ledger.models import LedgerEvent
        from tallyproof_core.hashing import leaf_hash
        from tallyproof_core.merkle import verify_inclusion

        rows = LedgerEvent.objects.filter(public_id__in=event_ids).only(
            "canonical_bytes", "leaf_index"
        )
        found = list(rows)
        if len(found) != len(event_ids):
            return False
        size = self.checkpoint.tree_size
        return all(
            row.leaf_index < size
            and verify_inclusion(
                leaf_hash(bytes(row.canonical_bytes)),
                row.leaf_index,
                size,
                self.tree.inclusion_proof(row.leaf_index, size),
                self.checkpoint.root_hash,
            )
            for row in found
        )


def _observe(answer: Any, integrity: Integrity, tokens: int, elapsed_ms: int) -> Observed:  # noqa: ANN401
    from apps.analyst.answer import CITE, SLOT

    evidence = answer.evidence
    final = answer.trace.verdicts[-1] if answer.trace.verdicts else None
    used: list[str] = []
    cited: set[str] = set()
    quotes: list[tuple[str, str]] = []
    sections: list[str] = []
    leaf_text_ok = True
    if evidence is not None and final is not None and answer.status == "answered":
        text = " ".join(final.sentences)
        used = [str(evidence.slots[s].value) for s in SLOT.findall(text) if s in evidence.slots]
        for label in CITE.findall(text):
            if label in evidence.citations:
                cited.update(evidence.citations[label].event_ids)
            elif label in evidence.sources:
                sections.append(evidence.sources[label].section)
                cited.add(evidence.sources[label].event_id)
        for quote in answer.quotes:
            source = evidence.sources.get(quote.source)
            if source is not None:
                quotes.append((source.section, quote.text))
                cited.add(source.event_id)
                leaf_text_ok &= " ".join(quote.text.split()) in " ".join(source.leaf_text.split())
    return Observed(
        status=answer.status,
        refusal=answer.refusal,
        text=answer.text,
        used_values=used,
        cited=cited,
        quotes=quotes,
        sections_cited=sections,
        fallback=answer.trace.used_fallback,
        first_free_numbers=answer.trace.verdicts[0].free_numbers if answer.trace.verdicts else 0,
        drafts=len(answer.trace.verdicts),
        final_ok=bool(final and final.ok),
        tokens=tokens,
        latency_ms=elapsed_ms,
        integrity_ok=leaf_text_ok and integrity.events(cited),
    )


def _reconciliation(oracle: Oracle) -> dict[str, Any]:
    from apps.reconciliation.models import BreakEvent

    found = {
        (link.recon_break.break_type, link.event.public_id)
        for link in BreakEvent.objects.select_related("recon_break", "event")
    }
    labeled = [x for x in oracle.labels if x["anomaly"] in RECONCILED and x["event_id"]]
    caught = sum((RECONCILED[x["anomaly"]], x["event_id"]) in found for x in labeled)
    return {
        "reconciliation_recall": round(caught / len(labeled), 4) if labeled else None,
        "break_types_found": len({b for b, _ in found}),
    }


def ask_all(
    questions: list[tuple[str, Question]],
    oracle: Oracle,
    meter: Meter,
    models: "Models",
    built: harness.Built,
    progress: Callable[[str], None],
) -> list[tuple[str, Result]]:
    """Ask every question through the real pipeline and score it."""
    from apps.analyst.pipeline import ask
    from apps.analyst.service import AnalystConnection, agencies, search_policy

    executor = AnalystConnection("analyst")
    names = agencies(executor)
    integrity = Integrity(built)
    results = []
    for n, (set_name, q) in enumerate(questions, start=1):
        before, started = meter.tokens, time.monotonic()
        answer = ask(
            q.text, client=meter, executor=executor, search=search_policy, models=models,
            agencies=names, tree_size=built.tree_size,
        )  # fmt: skip
        elapsed = int((time.monotonic() - started) * 1000)
        observed = _observe(answer, integrity, meter.tokens - before, elapsed)
        result = score(
            q.id, q.text, q.category, q.answerable, oracle.expected(q.expect), observed,
            q.must_not_say,
        )  # fmt: skip
        results.append((set_name, result))
        progress(f"[{n}/{len(questions)}] {q.id} {result.status} {result.refusal or ''}".rstrip())
    return results


def report(
    results: list[tuple[str, Result]],
    mode: str,
    meter: Meter,
    models: "Models",
    extra: dict[str, Any],
) -> dict[str, Any]:
    """Metrics per question set, the template versus held-out gap, and the gate."""
    harness_check = mode == "fake" or meter.misses > 0
    by_set: dict[str, list[Result]] = {}
    for set_name, result in results:
        by_set.setdefault(set_name, []).append(result)
    sets = {name: metrics(rows) for name, rows in by_set.items()}
    every = metrics([r for _, r in results]) | extra
    failures = gate(every, quality=not harness_check)
    gap = None
    if "held_out" in sets and len(sets) > 1:
        template = next(v for k, v in sets.items() if k != "held_out")
        a, b = template.get("numeric_exactness"), sets["held_out"].get("numeric_exactness")
        gap = round(a - b, 4) if a is not None and b is not None else None
    return {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": mode,
        "label": "harness check" if harness_check else "quality run",
        "cache_misses": meter.misses,
        "models": {"router": models.router, "answer": models.answer},
        "metrics": every,
        "by_set": sets,
        "template_vs_held_out_numeric_gap": gap,
        "gate_failures": failures,
        "results": [{"set": s, **as_dict(r)} for s, r in results],
    }


def markdown(data: dict[str, Any]) -> str:
    """A readable report."""
    lines = [
        f"# Evaluation, {data['run_at']}",
        "",
        f"Mode `{data['mode']}`, labeled **{data['label']}**. Models: router "
        f"`{data['models']['router']}`, answer `{data['models']['answer']}`. "
        f"Cache misses: {data['cache_misses']}.",
        "",
        "| Metric | " + " | ".join(["all", *data["by_set"]]) + " |",
        "|---|" + "---|" * (1 + len(data["by_set"])),
    ]
    for name, value in data["metrics"].items():
        row = [value, *(s.get(name, "") for s in data["by_set"].values())]
        lines.append(f"| {name} | " + " | ".join("" if v is None else str(v) for v in row) + " |")
    lines += [
        "",
        "Gate: " + ("passed" if not data["gate_failures"] else "; ".join(data["gate_failures"])),
        "",
    ]
    lines += [
        "## Per question",
        "",
        "| Set | ID | Status | Numeric | Cited | Answer |",
        "|---|---|---|---|---|---|",
    ]
    for r in data["results"]:
        answer = (r["answer"] or r["refusal"] or "").replace("|", "/")[:120]
        lines.append(
            f"| {r['set']} | {r['id']} | {r['status']} | {r['numeric_exact']} | "
            f"{r['cited_correct']}/{r['must']} | {answer} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - exercised by `make eval`
    """Run one evaluation and write its reports."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", choices=sorted(SETS), default="smoke")
    parser.add_argument("--mode", choices=["fake", "cached", "live"], default="cached")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    questions = [(p.stem, q) for p in SETS[args.set] for q in load(p)]
    oracle = Oracle()
    with harness.database():
        built = harness.build()
        print(f"ledger built: {built.events} events, {built.policy_sections} FAR leaves, "
              f"checkpoint at {built.tree_size}")  # fmt: skip
        meter, models = _client(args.mode)
        results = ask_all(questions, oracle, meter, models, built, print)
        data = report(results, args.mode, meter, models, _reconciliation(oracle))
    folder = args.out / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "report.json").write_text(json.dumps(data, indent=2, default=str) + "\n")
    (folder / "report.md").write_text(markdown(data))
    print(markdown(data).split("## Per question")[0])
    print(f"reports in {folder}")
    return 1 if data["gate_failures"] else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
