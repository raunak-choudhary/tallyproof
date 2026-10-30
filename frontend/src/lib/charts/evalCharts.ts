/**
 * Layouts for the evaluation dashboard. Pure functions: data in, geometry out; the
 * components only render and handle input.
 *
 * - Parallel coordinates: every run across every quality metric at once, one polyline
 *   per run, the gate marked on each axis. A weak metric shows as a dip.
 * - Horizon charts: one metric over runs, folded into bands around its gate, so many
 *   metrics fit in little height and the sign (above or below the gate) reads by colour.
 * - Slope chart: per category, the share right in one run against another.
 * - Heat matrix: questions by runs, coloured by outcome, so a miss that repeats in every
 *   run reads differently from one that comes and goes.
 */

import { area, curveMonotoneX, line, scaleLinear, scalePoint } from "d3";

import type { EvalResult, Metric, Outcome } from "@/lib/evals/reports";
import { outcome } from "@/lib/evals/reports";

export interface Box {
  width: number;
  height: number;
}

// ---------------------------------------------------------------- parallel coordinates

export interface ParallelRun {
  id: string;
  metrics: Record<string, number | null>;
}

export interface ParallelLayout {
  axes: { key: string; label: string; x: number; gateY: number | null }[];
  lines: { id: string; path: string }[];
  y: (value: number) => number;
  /** The value an axis position stands for, for brushing. */
  invert: (y: number) => number;
  top: number;
  bottom: number;
}

/** Values run from `floor` to 1; low-scoring early runs set the floor, rounded down. */
export function parallelLayout(
  runs: readonly ParallelRun[],
  metrics: readonly Metric[],
  gates: Record<string, number>,
  box: Box,
  margin = { top: 28, bottom: 28, side: 36 },
): ParallelLayout {
  const values = runs.flatMap((r) => metrics.map((m) => r.metrics[m.key])).filter(isNumber);
  const floor = Math.max(0, Math.floor(Math.min(1, ...values) * 10) / 10);
  const x = scalePoint<string>()
    .domain(metrics.map((m) => m.key))
    .range([margin.side, box.width - margin.side]);
  const y = scaleLinear()
    .domain([floor, 1])
    .range([box.height - margin.bottom, margin.top])
    .clamp(true);
  const draw = line<[string, number | null]>()
    .defined(([, v]) => v !== null)
    .x(([k]) => x(k)!)
    .y(([, v]) => y(v!));
  return {
    axes: metrics.map((m) => ({
      key: m.key,
      label: m.short,
      x: x(m.key)!,
      gateY: gates[m.key] === undefined ? null : y(gates[m.key]!),
    })),
    lines: runs.map((r) => ({
      id: r.id,
      path: draw(metrics.map((m) => [m.key, r.metrics[m.key] ?? null])) ?? "",
    })),
    y,
    invert: (py) => y.invert(py),
    top: margin.top,
    bottom: box.height - margin.bottom,
  };
}

/** Runs whose value on every brushed axis lies inside its range. A missing value fails. */
export function brushed(
  runs: readonly ParallelRun[],
  ranges: Readonly<Record<string, readonly [number, number]>>,
): Set<string> {
  const keys = Object.keys(ranges);
  return new Set(
    runs
      .filter((r) =>
        keys.every((k) => {
          const v = r.metrics[k];
          const [lo, hi] = ranges[k]!;
          return isNumber(v) && v >= Math.min(lo, hi) && v <= Math.max(lo, hi);
        }),
      )
      .map((r) => r.id),
  );
}

// ---------------------------------------------------------------- horizon charts

export interface HorizonLayout {
  /** Bands, the lightest first so darker ones paint over them. */
  bands: { sign: 1 | -1; level: number; path: string }[];
  points: { x: number; value: number | null }[];
  bandSize: number;
}

/**
 * One metric over runs as a horizon chart around `gate`. The distance from the gate is
 * cut into `levels` bands of `bandSize`; each band is drawn over the full height, so a
 * value two bands above the gate shows as two stacked shades. Below the gate draws the
 * same way in the other colour.
 */
export function horizonLayout(
  values: readonly (number | null)[],
  gate: number,
  box: Box,
  levels = 3,
  bandSize = 0.05,
): HorizonLayout {
  const x = scaleLinear()
    .domain([0, Math.max(1, values.length - 1)])
    .range([0, box.width]);
  const y = scaleLinear().domain([0, bandSize]).range([box.height, 0]);
  const bands: HorizonLayout["bands"] = [];
  for (const sign of [1, -1] as const) {
    for (let level = 0; level < levels; level++) {
      const part = (v: number | null) => {
        if (v === null) return 0;
        // Rounded to a millionth so 1.00 against a 0.95 gate fills exactly one band.
        const d = Math.round(((v - gate) * sign - level * bandSize) * 1e6) / 1e6;
        return Math.max(0, Math.min(bandSize, d));
      };
      const draw = area<number | null>()
        .defined((v) => v !== null)
        .x((_, i) => x(i))
        .y0(box.height)
        .y1((v) => y(part(v)))
        .curve(curveMonotoneX);
      const path = draw([...values]) ?? "";
      if (values.some((v) => part(v) > 1e-9)) bands.push({ sign, level, path });
    }
  }
  return { bands, points: values.map((v, i) => ({ x: x(i), value: v })), bandSize };
}

// ---------------------------------------------------------------- slope chart

export interface SlopeItem {
  key: string;
  left: number | null;
  right: number | null;
}

export interface SlopeLayout {
  lines: {
    key: string;
    y1: number | null;
    y2: number | null;
    /** Label positions, pushed apart so they never overlap. */
    ly1: number | null;
    ly2: number | null;
    change: number | null;
  }[];
  y: (v: number) => number;
}

/** Spread label positions at least `gap` apart, keeping their order, within [min, max]. */
export function dodge(ys: readonly number[], gap: number, min: number, max: number): number[] {
  const order = ys.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y);
  const placed = order.map((o) => o.y);
  for (let k = 1; k < placed.length; k++) placed[k] = Math.max(placed[k]!, placed[k - 1]! + gap);
  const overflow = (placed.at(-1) ?? 0) - max;
  if (overflow > 0) {
    placed[placed.length - 1] = max;
    for (let k = placed.length - 2; k >= 0; k--)
      placed[k] = Math.min(placed[k]!, placed[k + 1]! - gap);
  }
  for (let k = 0; k < placed.length; k++) placed[k] = Math.max(min, placed[k]!);
  const out = new Array<number>(ys.length);
  order.forEach((o, k) => (out[o.i] = placed[k]!));
  return out;
}

export function slopeLayout(items: readonly SlopeItem[], box: Box, gap = 14): SlopeLayout {
  const y = scaleLinear()
    .domain([0, 1])
    .range([box.height - 10, 10]);
  const at = (v: number | null) => (v === null ? null : y(v));
  const spread = (side: "left" | "right") => {
    const present = items.map((it, i) => ({ v: at(it[side]), i })).filter((p) => p.v !== null);
    const moved = dodge(
      present.map((p) => p.v!),
      gap,
      10,
      box.height - 10,
    );
    const out = new Array<number | null>(items.length).fill(null);
    present.forEach((p, k) => (out[p.i] = moved[k]!));
    return out;
  };
  const l = spread("left");
  const r = spread("right");
  return {
    lines: items.map((it, i) => ({
      key: it.key,
      y1: at(it.left),
      y2: at(it.right),
      ly1: l[i]!,
      ly2: r[i]!,
      change: it.left !== null && it.right !== null ? it.right - it.left : null,
    })),
    y,
  };
}

// ---------------------------------------------------------------- heat matrix

export interface MatrixCell {
  outcome: Outcome;
  result: EvalResult;
}

export interface MatrixRow {
  id: string;
  question: string;
  category: string;
  /** One cell per run; null where the run didn't ask this question. */
  cells: (MatrixCell | null)[];
  /** Every run that asked it went the same way. */
  steady: boolean;
  /** Runs that asked it and got it wrong. */
  misses: number;
}

const GOOD: ReadonlySet<Outcome> = new Set(["right", "refused"]);

/** Questions by runs. Rows keep the question order of the latest run that asked them. */
export function questionMatrix(runs: readonly { results: readonly EvalResult[] }[]): MatrixRow[] {
  const order: string[] = [];
  const seen = new Set<string>();
  for (const run of [...runs].reverse()) {
    for (const r of run.results) {
      const key = `${r.set}/${r.id}`;
      if (!seen.has(key)) {
        seen.add(key);
        order.push(key);
      }
    }
  }
  const lookup = runs.map((run) => new Map(run.results.map((r) => [`${r.set}/${r.id}`, r])));
  return order.map((key) => {
    const cells = lookup.map((m): MatrixCell | null => {
      const r = m.get(key);
      return r ? { outcome: outcome(r), result: r } : null;
    });
    const asked = cells.filter((c): c is MatrixCell => c !== null);
    const first = asked[0]!.result;
    return {
      id: first.id,
      question: first.question,
      category: first.category,
      cells,
      steady: asked.every((c) => c.outcome === asked[0]!.outcome),
      misses: asked.filter((c) => !GOOD.has(c.outcome)).length,
    };
  });
}

function isNumber(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}
