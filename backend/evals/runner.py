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
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from evals import harness, judge, naive
from evals.dataset import DEMO_DIR
from evals.dataset import OUT_DIR as EVAL_DIR
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


def demo_questions(oracle: Oracle) -> list[Question]:
    """The smoke-shaped set generated from the dataset, plus totals that pass the citation cap.

    Template sampling can land on small agencies, which would measure nothing about
    large totals, so the two agencies with the most records always get a total and a
    count, and one question ranks every agency.
    """
    from collections import Counter

    from evals import golden

    smoke, _ = golden.build(oracle)
    rows = [{**row, "set": "demo"} for row in smoke]
    sizes = Counter(
        r.fields["awarding_agency"]
        for r in oracle.records
        if r.event_type.startswith("obligation.") and r.fields.get("awarding_agency")
    )
    large = [agency for agency, _ in sizes.most_common(2)]
    n = 0
    for agency in large:
        for text, kind in (
            (f"What has {agency} obligated in total?", "sum"),
            (f"How many contract actions has {agency} recorded?", "count"),
        ):
            n += 1
            expect = {"kind": kind, "entity": "obligations", "awarding_agency": agency}
            rows.append(
                {"id": f"L{n:03d}", "text": text, "category": "numeric_aggregate", "expect": expect}
            )
    rows.append(
        {
            "id": f"L{n + 1:03d}",
            "text": "Which agency has obligated the most, and how much?",
            "category": "numeric_aggregate",
            "expect": {"kind": "top", "entity": "obligations", "group_by": "awarding_agency"},
        }
    )
    return [
        Question(
            id=row["id"],
            text=row["text"],
            category=row["category"],
            expect=row["expect"],
            must_not_say=tuple(row.get("must_not_say", ())),
        )
        for row in rows
    ]


def fake_script(request: Any) -> str:  # noqa: ANN401 - an LLMRequest; typed loosely to stay import-free
    """Scripted replies that exercise every path without pretending to be good."""
    if request.prompt_version.startswith("router"):
        return json.dumps({"category": "refusal", "refusal_reason": "no_data"})
    if request.prompt_version.startswith("fallback"):
        return json.dumps({"sql": "SELECT 1"})
    if request.prompt_version.startswith("judge"):
        return json.dumps({"verdicts": []})
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


def _judge_model(mode: str) -> str | None:
    """The judge's model: recorded with the cache on replay, from settings when live."""
    from config.env import llm_settings

    settings = llm_settings()
    if mode == "fake":
        return "fake-judge"
    if mode == "cached":
        manifest = settings.llm_cache_dir / "manifest.json"
        recorded = json.loads(manifest.read_text()) if manifest.exists() else {}
        return recorded.get("judge_model") or None
    return settings.llm_judge_model or None


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
                "judge_model": settings.llm_judge_model,
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
        # The rendered text carries a citation for every value it shows.
        for label in CITE.findall(answer.text):
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
        sampled=bool(evidence is not None and evidence.sampled),
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


def judged(
    meter: Meter, model: str | None, max_tokens: int, question: str, result: Result, evidence: str
) -> float | None:
    """The judge's faithfulness score for one answered question, or None when not judged."""
    if model is None or result.status != "answered" or not judge.sentences(result.answer):
        return None
    reply = meter.complete(judge.request(question, result.answer, evidence, model, max_tokens))
    return judge.score(reply.text, len(judge.sentences(result.answer)))


def ask_all(
    questions: list[tuple[str, Question]],
    oracle: Oracle,
    meter: Meter,
    models: "Models",
    built: harness.Built,
    progress: Callable[[str], None],
    system: str = "analyst",
    judge_model: str | None = None,
) -> list[tuple[str, Result]]:
    """Ask every question through the analyst (or the naive baseline) and score it."""
    from apps.analyst.pipeline import _evidence_block, ask
    from apps.analyst.service import AnalystConnection, agencies, search_policy

    executor = AnalystConnection("analyst")
    names = agencies(executor)
    integrity = Integrity(built)
    results = []
    for n, (set_name, q) in enumerate(questions, start=1):
        before, started = meter.tokens, time.monotonic()
        if system == "naive":
            context = naive.retrieve(q.text, executor, search_policy, names)
            reply = meter.complete(
                naive.request(
                    q.text, context, models.answer, models.max_output_tokens,
                    models.reasoning_effort,
                )
            )  # fmt: skip
            elapsed = int((time.monotonic() - started) * 1000)
            observed = naive.observe(
                reply.text, context, integrity.events, meter.tokens - before, elapsed
            )
            evidence = context.render()
        else:
            answer = ask(
                q.text, client=meter, executor=executor, search=search_policy, models=models,
                agencies=names, tree_size=built.tree_size,
            )  # fmt: skip
            elapsed = int((time.monotonic() - started) * 1000)
            observed = _observe(answer, integrity, meter.tokens - before, elapsed)
            evidence = _evidence_block(answer.evidence) if answer.evidence else ""
        result = score(
            q.id, q.text, q.category, q.answerable, oracle.expected(q.expect), observed,
            q.must_not_say,
        )  # fmt: skip
        result.faithfulness = judged(
            meter, judge_model, models.max_output_tokens, q.text, result, evidence
        )
        results.append((set_name, result))
        progress(f"[{n}/{len(questions)}] {q.id} {result.status} {result.refusal or ''}".rstrip())
    return results


def _commit() -> str:
    """The commit being measured: CI's, or the working tree's HEAD."""
    sha = os.environ.get("CIRCLE_SHA1")
    if sha:
        return sha
    try:
        git = shutil.which("git")
        if git is None:
            return "unknown"
        out = subprocess.run(  # noqa: S603 - fixed arguments, resolved executable
            [git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=10
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def report(
    results: list[tuple[str, Result]],
    mode: str,
    meter: Meter,
    models: "Models",
    extra: dict[str, Any],
    system: str = "analyst",
    judge_model: str | None = None,
) -> dict[str, Any]:
    """Metrics per question set, the template versus held-out gap, and the gate.

    The naive baseline is never gated: it is there to be compared, and falling short is
    its expected result. Its runs are labeled baseline runs.
    """
    harness_check = mode == "fake" or meter.misses > 0
    by_set: dict[str, list[Result]] = {}
    for set_name, result in results:
        by_set.setdefault(set_name, []).append(result)
    sets = {name: metrics(rows) for name, rows in by_set.items()}
    every = metrics([r for _, r in results]) | extra
    failures = [] if system == "naive" else gate(every, quality=not harness_check)
    gap = None
    if "held_out" in sets and len(sets) > 1:
        template = next(v for k, v in sets.items() if k != "held_out")
        a, b = template.get("numeric_exactness"), sets["held_out"].get("numeric_exactness")
        gap = round(a - b, 4) if a is not None and b is not None else None
    return {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": _commit(),
        "mode": mode,
        "system": system,
        "label": "harness check"
        if harness_check
        else ("baseline run" if system == "naive" else "quality run"),
        "cache_misses": meter.misses,
        "models": {"router": models.router, "answer": models.answer, "judge": judge_model},
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
        f"System `{data.get('system', 'analyst')}`, mode `{data['mode']}`, labeled "
        f"**{data['label']}**. Models: router `{data['models']['router']}`, answer "
        f"`{data['models']['answer']}`, judge `{data['models'].get('judge') or 'none'}`. "
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
    parser.add_argument(
        "--system",
        choices=["analyst", "naive"],
        default="analyst",
        help="analyst: the real pipeline; naive: the retrieval baseline it is compared with",
    )
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--scale",
        choices=["eval", "demo"],
        default="eval",
        help="eval: the committed dataset; demo: the first 20,000 gold events, as the demo runs",
    )
    args = parser.parse_args(argv)
    dataset = DEMO_DIR if args.scale == "demo" else EVAL_DIR
    if not (dataset / "events.jsonl.gz").exists():
        print(f"no dataset at {dataset}; run make eval-dataset SCALE={args.scale}")
        return 2
    oracle = Oracle(dataset)
    if args.scale == "demo":
        questions = [("demo", q) for q in demo_questions(oracle)]
    else:
        questions = [(p.stem, q) for p in SETS[args.set] for q in load(p)]
    with harness.database():
        built = harness.build(dataset)
        print(f"ledger built: {built.events} events, {built.policy_sections} FAR leaves, "
              f"checkpoint at {built.tree_size}")  # fmt: skip
        meter, models = _client(args.mode)
        judge_model = _judge_model(args.mode)
        results = ask_all(questions, oracle, meter, models, built, print, args.system, judge_model)
        data = report(
            results, args.mode, meter, models, _reconciliation(oracle), args.system, judge_model
        )
    folder = args.out / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "report.json").write_text(json.dumps(data, indent=2, default=str) + "\n")
    (folder / "report.md").write_text(markdown(data))
    print(markdown(data).split("## Per question")[0])
    print(f"reports in {folder}")
    return 1 if data["gate_failures"] else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
