"use client";

import { useEffect, useMemo, useState } from "react";

import { questionMatrix } from "@/lib/charts/evalCharts";
import type { EvalIndex, RunReport } from "@/lib/evals/reports";
import {
  categoryRates,
  INTEGRITY_METRICS,
  loadIndex,
  loadRun,
  QUALITY_METRICS,
  runLabel,
} from "@/lib/evals/reports";

import { HorizonMetrics } from "./HorizonMetrics";
import { ParallelRuns } from "./ParallelRuns";
import { QuestionMatrix } from "./QuestionMatrix";
import { SlopeCategories } from "./SlopeCategories";

const HEADLINE = ["numeric_exactness", "citation_precision", "citation_recall", "refusal_f1"];

// The published evaluation runs, read from the exported reports. Quality is scored against
// an oracle that never sees the analyst's code; integrity is shown on its own, since it is
// guaranteed by construction and says nothing about whether answers are good.
export function EvalsPage() {
  const [index, setIndex] = useState<EvalIndex | null>(null);
  const [reports, setReports] = useState<RunReport[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [compare, setCompare] = useState<string | null>(null);

  useEffect(() => {
    loadIndex()
      .then(async (idx) => {
        setIndex(idx);
        setReports(await Promise.all(idx.runs.map((r) => loadRun(r.file))));
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const runs = useMemo(() => index?.runs ?? [], [index]);
  const ids = useMemo(() => runs.map((r) => r.file), [runs]);
  const labels = useMemo(
    () => Object.fromEntries(runs.map((r) => [r.file, runLabel(r.run_at)])),
    [runs],
  );
  const gates = useMemo(() => index?.gates?.quality ?? {}, [index]);
  const parallel = useMemo(() => runs.map((r) => ({ id: r.file, metrics: r.metrics })), [runs]);
  const matrix = useMemo(() => (reports ? questionMatrix(reports) : []), [reports]);

  if (error) {
    return (
      <p role="alert" className="text-fail">
        Could not load the evaluation reports: {error}
      </p>
    );
  }
  if (!index || !reports) return <p className="text-fg-muted">Loading the published runs…</p>;
  if (runs.length === 0) return <p className="text-fg-muted">No runs have been published yet.</p>;

  const current = selected ?? ids.at(-1)!;
  const base = compare ?? ids[0]!;
  const at = ids.indexOf(current);
  const run = runs[at]!;
  const report = reports[at]!;
  const baseReport = reports[ids.indexOf(base)]!;
  const sets = Object.entries(run.sets)
    .map(([name, n]) => `${n ?? 0} ${name.replace(/_/g, "-")}`)
    .join(", ");

  return (
    <div className="grid gap-10">
      <section aria-label="Run" className="grid gap-4">
        <div className="flex flex-wrap items-end gap-4">
          <label className="grid gap-1 text-xs text-fg-muted">
            Run
            <select
              value={current}
              onChange={(e) => setSelected(e.target.value)}
              className="rounded-[var(--radius-sm)] border border-border bg-bg-elevated px-2 py-1.5 font-mono text-sm text-fg"
            >
              {ids.map((id, i) => (
                <option key={id} value={id}>
                  {i + 1}. {labels[id]}
                </option>
              ))}
            </select>
          </label>
          <p className="min-w-0 text-xs text-fg-muted">
            <span className="breakable">
              {sets} questions · answer model <code className="font-mono">{run.models.answer}</code>{" "}
              · commit <code className="font-mono">{run.commit.slice(0, 7)}</code> · {run.mode}
            </span>
            <span
              className={`ml-2 inline-block rounded-full border border-border bg-bg-elevated px-2 py-0.5 font-medium ${
                run.gate_failures.length ? "text-warn" : "text-ok"
              }`}
            >
              {run.gate_failures.length
                ? `${run.gate_failures.length} gate${run.gate_failures.length > 1 ? "s" : ""} below threshold`
                : "every gate passed"}
            </span>
          </p>
        </div>

        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
          <div className="rounded-[var(--radius)] border border-border bg-bg-elevated p-4">
            <p className="text-xs font-semibold tracking-[0.12em] text-accent-2 uppercase">
              Integrity
            </p>
            <p className="mt-1 text-xs text-fg-muted">
              Guaranteed by how the system is built: every cited record verified. Not a measure of
              answer quality.
            </p>
            <dl className="mt-3 grid grid-cols-2 gap-3">
              {INTEGRITY_METRICS.map((m) => (
                <div key={m.key}>
                  <dt className="text-xs text-fg-muted">{m.label}</dt>
                  <dd className="font-mono text-xl tabular-nums">
                    {run.metrics[m.key]?.toFixed(2) ?? "n/a"}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="rounded-[var(--radius)] border border-border bg-bg-elevated p-4">
            <p className="text-xs font-semibold tracking-[0.12em] text-accent-2 uppercase">
              Quality
            </p>
            <p className="mt-1 text-xs text-fg-muted">
              Scored against an oracle that shares no code with the analyst.
            </p>
            <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {HEADLINE.map((key) => {
                const m = QUALITY_METRICS.find((q) => q.key === key)!;
                const v = run.metrics[key];
                const gate = gates[key];
                const below = v !== null && v !== undefined && gate !== undefined && v < gate;
                return (
                  <div key={key}>
                    <dt className="text-xs text-fg-muted">{m.label}</dt>
                    <dd className={`font-mono text-xl tabular-nums ${below ? "text-warn" : ""}`}>
                      {v?.toFixed(2) ?? "n/a"}
                    </dd>
                    {gate !== undefined && (
                      <dd className="text-xs text-fg-muted">gate {gate.toFixed(2)}</dd>
                    )}
                  </div>
                );
              })}
            </dl>
          </div>
        </div>
      </section>

      <section aria-label="Runs over time" className="grid gap-8 lg:grid-cols-2">
        <div className="hidden min-w-0 md:block lg:col-span-2">
          <ParallelRuns
            runs={parallel}
            metrics={QUALITY_METRICS}
            gates={gates}
            selected={current}
            labels={labels}
            onSelect={setSelected}
          />
        </div>
        <div className="min-w-0">
          <HorizonMetrics
            metrics={QUALITY_METRICS}
            gates={gates}
            runs={parallel}
            selectedIndex={at}
            labels={labels}
            onSelect={setSelected}
          />
          <p className="mt-2 text-xs text-fg-muted md:hidden">
            On a wider screen the runs also draw as parallel coordinates you can filter.
          </p>
        </div>
        <div className="grid min-w-0 content-start gap-3">
          <label className="grid w-fit gap-1 text-xs text-fg-muted">
            Compare with
            <select
              value={base}
              onChange={(e) => setCompare(e.target.value)}
              className="rounded-[var(--radius-sm)] border border-border bg-bg-elevated px-2 py-1.5 font-mono text-sm text-fg"
            >
              {ids.map((id, i) => (
                <option key={id} value={id}>
                  {i + 1}. {labels[id]}
                </option>
              ))}
            </select>
          </label>
          <SlopeCategories
            left={categoryRates(baseReport.results)}
            right={categoryRates(report.results)}
            leftLabel={`run ${ids.indexOf(base) + 1}`}
            rightLabel={`run ${at + 1}`}
          />
        </div>
      </section>

      <section aria-label="Questions">
        <QuestionMatrix rows={matrix} runIds={ids} labels={labels} selectedRun={current} />
      </section>

      <section aria-labelledby="evals-notes" className="grid gap-2 text-sm text-fg-muted">
        <h2 id="evals-notes" className="text-base font-semibold text-fg">
          What these runs are, and aren&apos;t
        </h2>
        <p>
          These are the live runs of the 20-question smoke set on 29 October 2026, published as they
          came out, early failures included: the first run scored 0.18 on numeric exactness, and the
          fixes between runs are in the commit history. The held-out set and the full 218-question
          run join this page once their runs are published, with the template against held-out gap
          beside them.
        </p>
      </section>
    </div>
  );
}
