"use client";

import { useEffect, useMemo, useState } from "react";

import { questionMatrix } from "@/lib/charts/evalCharts";
import type { EvalIndex, RunReport } from "@/lib/evals/reports";
import {
  bySystem,
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

const FAITHFULNESS = {
  key: "narrative_faithfulness",
  label: "Narrative faithfulness (judged)",
  short: "Faithful",
};

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
        setReports(await Promise.all(bySystem(idx.runs).analyst.map((r) => loadRun(r.file))));
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const runs = useMemo(() => bySystem(index?.runs ?? []).analyst, [index]);
  const baseline = useMemo(() => bySystem(index?.runs ?? []).naive.at(-1) ?? null, [index]);
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
    <div className="grid min-w-0 gap-10">
      <section aria-label="Run" className="grid min-w-0 gap-4">
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

      {baseline && (
        <section aria-labelledby="baseline-heading" className="grid gap-3">
          <h2 id="baseline-heading" className="text-base font-semibold">
            Against a naive baseline
          </h2>
          <p className="max-w-[65ch] text-sm text-fg-muted">
            The same questions, answered by retrieving rows and passages and letting the model
            answer and cite freely: no query spec, no bound values, no verifier. Run{" "}
            {runLabel(baseline.run_at)} with{" "}
            <code className="font-mono">{baseline.models.answer}</code>.
          </p>
          <div
            className="overflow-x-auto"
            tabIndex={0}
            aria-label="Baseline comparison, scrolls sideways"
          >
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-fg-muted">
                <tr>
                  <th scope="col" className="py-2 pr-4 font-medium">
                    Metric
                  </th>
                  <th scope="col" className="py-2 pr-4 font-medium">
                    Analyst, run {at + 1}
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    Naive baseline
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border font-mono tabular-nums">
                {[...QUALITY_METRICS, ...INTEGRITY_METRICS.slice(0, 1), FAITHFULNESS].map((m) => (
                  <tr key={m.key}>
                    <th scope="row" className="py-1.5 pr-4 font-sans font-normal">
                      {m.label}
                    </th>
                    <td className="py-1.5 pr-4">{run.metrics[m.key]?.toFixed(2) ?? "n/a"}</td>
                    <td className="py-1.5">{baseline.metrics[m.key]?.toFixed(2) ?? "n/a"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section aria-label="Questions" className="min-w-0">
        <QuestionMatrix rows={matrix} runIds={ids} labels={labels} selectedRun={current} />
      </section>

      <section aria-labelledby="evals-notes" className="grid gap-2 text-sm text-fg-muted">
        <h2 id="evals-notes" className="text-base font-semibold text-fg">
          What these runs are, and aren&apos;t
        </h2>
        <p>
          Runs 1 to 10 are live runs of the 20-question smoke set on 29 October 2026, published as
          they came out, early failures included: the first scored 0.18 on numeric exactness, and
          the fixes between runs are in the commit history. Runs 11 and 12 are all 218 questions,
          template and held-out: the first was blind, answered over three nights, and the second was
          scored after the fixes it led to. The held-out questions score well below the template
          ones; the results page in the docs goes through every miss.
        </p>
      </section>
    </div>
  );
}
