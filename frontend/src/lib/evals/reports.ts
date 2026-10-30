/**
 * Exported evaluation reports: the index the dashboard lists runs from, each run's full
 * report, and the pure helpers that turn results into what the charts draw. Reports are
 * published deliberately by `make eval-export`; see docs/evaluation.md.
 */

import { replayBase } from "@/lib/replay/paths";

export interface Gates {
  integrity: Record<string, number>;
  quality: Record<string, number>;
}

export interface RunSummary {
  file: string;
  run_at: string;
  commit: string;
  mode: string;
  label: string;
  models: { router: string; answer: string };
  sets: Record<string, number | null>;
  metrics: Record<string, number | null>;
  template_vs_held_out_numeric_gap: number | null;
  gate_failures: string[];
}

export interface EvalIndex {
  runs: RunSummary[];
  gates?: Gates;
}

export interface EvalResult {
  set: string;
  id: string;
  question: string;
  category: string;
  answerable: boolean;
  status: string;
  refusal: string | null;
  numeric_exact: boolean | null;
  must: number;
  cited: number;
  cited_correct: number;
  cited_allowed: number;
  policy_section_ok: boolean | null;
  quotes_faithful: boolean | null;
  injection_ok: boolean | null;
  integrity_ok: boolean;
  answer: string;
  tokens: number;
  latency_ms: number;
}

export interface RunReport {
  run_at: string;
  commit?: string;
  mode: string;
  label: string;
  models: { router: string; answer: string };
  metrics: Record<string, number | null>;
  by_set: Record<string, Record<string, number | null>>;
  gate_failures: string[];
  results: EvalResult[];
}

export interface Metric {
  key: string;
  label: string;
  short: string;
}

/** The quality metrics, in the order the charts show them. Integrity is kept apart. */
export const QUALITY_METRICS: readonly Metric[] = [
  { key: "numeric_exactness", label: "Numeric exactness", short: "Numbers" },
  { key: "citation_precision", label: "Citation precision", short: "Cite prec." },
  { key: "citation_recall", label: "Citation recall", short: "Cite recall" },
  { key: "answer_coverage", label: "Answer coverage", short: "Coverage" },
  { key: "refusal_f1", label: "Refusal F1", short: "Refusals" },
  { key: "anomaly_recall", label: "Anomaly recall", short: "Anomalies" },
  { key: "quote_faithfulness", label: "Quote faithfulness", short: "Quotes" },
  { key: "injection_resistance", label: "Injection resistance", short: "Injection" },
];

export const INTEGRITY_METRICS: readonly Metric[] = [
  { key: "integrity", label: "Integrity", short: "Integrity" },
  { key: "reconciliation_recall", label: "Reconciliation recall", short: "Recon." },
];

export function evalsBase(): string {
  return `${replayBase()}/evals`;
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`could not load ${url} (${response.status})`);
  return (await response.json()) as T;
}

export function loadIndex(base = evalsBase()): Promise<EvalIndex> {
  return fetchJson<EvalIndex>(`${base}/index.json`);
}

export function loadRun(file: string, base = evalsBase()): Promise<RunReport> {
  return fetchJson<RunReport>(`${base}/${file}`);
}

/**
 * How one question went. Integrity comes first: a cited record that fails to verify is
 * a failure whatever the prose says. A refusal is right only when the question had no
 * honest answer.
 */
export type Outcome = "right" | "missed" | "refused" | "wrong_refusal" | "integrity";

export function outcome(r: EvalResult): Outcome {
  if (!r.integrity_ok) return "integrity";
  if (r.status === "refused") return r.answerable ? "wrong_refusal" : "refused";
  if (!r.answerable) return "missed";
  const exact = r.numeric_exact !== false;
  const cited = r.must === 0 || r.cited_correct === r.must;
  const policy = r.policy_section_ok !== false && r.quotes_faithful !== false;
  return exact && cited && policy && r.injection_ok !== false ? "right" : "missed";
}

export const OUTCOMES: readonly { key: Outcome; label: string; colour: string }[] = [
  { key: "right", label: "Answered and scored right", colour: "var(--ok)" },
  { key: "refused", label: "Refused, rightly", colour: "var(--chart-2)" },
  { key: "missed", label: "A value or citation missed", colour: "var(--chart-4)" },
  { key: "wrong_refusal", label: "Refused an answerable question", colour: "var(--warn)" },
  { key: "integrity", label: "A cited record failed to verify", colour: "var(--fail)" },
];

export function outcomeInfo(key: Outcome) {
  return OUTCOMES.find((o) => o.key === key)!;
}

export interface CategoryRate {
  category: string;
  n: number;
  /** Share of the category's questions that went as they should. */
  right: number | null;
}

const rate = (hits: number, total: number) =>
  total ? Math.round((hits / total) * 10000) / 10000 : null;

/** Per category: the share of questions answered right or rightly refused. */
export function categoryRates(results: readonly EvalResult[]): CategoryRate[] {
  const groups = new Map<string, EvalResult[]>();
  for (const r of results) groups.set(r.category, [...(groups.get(r.category) ?? []), r]);
  return [...groups.entries()]
    .map(([category, rows]) => ({
      category,
      n: rows.length,
      right: rate(
        rows.filter((r) => ["right", "refused"].includes(outcome(r))).length,
        rows.length,
      ),
    }))
    .sort((a, b) => a.category.localeCompare(b.category));
}

/** A category name as the page says it. */
export function categoryLabel(category: string): string {
  return category.replace(/_/g, " ");
}

const when = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZone: "UTC",
});

/** A run's name on the page: its time in UTC. */
export function runLabel(runAt: string): string {
  return `${when.format(new Date(runAt))} UTC`;
}
