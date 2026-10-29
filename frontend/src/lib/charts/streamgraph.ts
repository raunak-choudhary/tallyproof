/**
 * A streamgraph of amounts over time by group: stacked areas on a wiggle baseline, so the
 * reader sees each group's share and the whole at once. Pure layout: rows in, drawn
 * paths and scales out. The component only renders.
 */

import {
  area,
  curveBasis,
  scaleLinear,
  scaleTime,
  stack,
  stackOffsetWiggle,
  stackOrderInsideOut,
  utcDay,
  utcMonth,
} from "d3";

import type { LedgerRow } from "@/lib/ledger/events";

export interface StreamLayer {
  group: string;
  /** Index into the chart colour tokens, 0 to 5. "Other" always takes the last. */
  colour: number;
  path: string;
  /** Per bin: the group's total, for the tooltip. */
  totals: { month: Date; amount: number }[];
}

export type BinKind = "month" | "day" | "leaf";

export interface StreamgraphLayout {
  layers: StreamLayer[];
  /** One entry per bin: a date for month and day bins, a leaf index for leaf bins. */
  months: Date[];
  kind: BinKind;
  width: number;
  height: number;
  /** x position for a month, for hover lookup. */
  x: (month: Date) => number;
  /** Total across all groups per month. */
  monthTotals: number[];
}

export const OTHER = "Other";

/**
 * Lay out rows as monthly stacked streams. The `top` largest groups by total amount get
 * their own stream; everything else folds into "Other". Negative amounts (deobligations)
 * reduce a group's month but a stream is never drawn below zero.
 */
export function streamgraphLayout(
  rows: readonly LedgerRow[],
  { width = 600, height = 200, top = 5 }: { width?: number; height?: number; top?: number } = {},
): StreamgraphLayout {
  if (rows.length === 0) {
    return { layers: [], months: [], kind: "month", width, height, x: () => 0, monthTotals: [] };
  }
  // Bin by month when the records span at least three months, by day when at least three
  // days, and by position in the log otherwise (a demo bundle is often a single day).
  const times = rows.map((r) => r.date.getTime());
  const lo = Math.min(...times);
  const hi = Math.max(...times);
  const DAY = 86_400_000;
  let kind: BinKind = "leaf";
  let months: Date[] = [];
  let binOf: (r: LedgerRow) => number;
  if (hi - lo >= 3 * 30 * DAY) {
    kind = "month";
    months = utcMonth.range(utcMonth.floor(new Date(lo)), utcMonth.ceil(new Date(hi + 1)));
    binOf = (r) => {
      const f = utcMonth.floor(r.date).getTime();
      const i = months.findIndex((m) => m.getTime() === f);
      return i < 0 ? months.length - 1 : i;
    };
  } else if (hi - lo >= 3 * DAY) {
    kind = "day";
    months = utcDay.range(utcDay.floor(new Date(lo)), utcDay.ceil(new Date(hi + 1)));
    binOf = (r) => {
      const f = utcDay.floor(r.date).getTime();
      const i = months.findIndex((m) => m.getTime() === f);
      return i < 0 ? months.length - 1 : i;
    };
  } else {
    const leaves = rows.map((r) => r.leafIndex);
    const minLeaf = Math.min(...leaves);
    const maxLeaf = Math.max(...leaves);
    const bins = Math.max(2, Math.min(40, maxLeaf - minLeaf + 1));
    const span = Math.max(1, maxLeaf - minLeaf + 1);
    months = Array.from(
      { length: bins },
      (_, i) => new Date(minLeaf + Math.floor((i * span) / bins)),
    );
    binOf = (r) => Math.min(bins - 1, Math.floor(((r.leafIndex - minLeaf) * bins) / span));
  }
  if (months.length === 0) months.push(new Date(lo));

  const byGroup = new Map<string, number>();
  for (const r of rows) byGroup.set(r.group, (byGroup.get(r.group) ?? 0) + Math.max(0, r.amount));
  const ranked = [...byGroup.entries()].sort((a, b) => b[1] - a[1]).map(([g]) => g);
  const keep = ranked.slice(0, top);
  const keys = ranked.length > top ? [...keep, OTHER] : keep;
  const label = (g: string) => (keep.includes(g) ? g : OTHER);

  const table = months.map((m) => {
    const cell: Record<string, number> = { time: m.getTime() };
    for (const k of keys) cell[k] = 0;
    return cell;
  });
  for (const r of rows) {
    const cell = table[binOf(r)];
    if (cell) cell[label(r.group)] = (cell[label(r.group)] ?? 0) + Math.max(0, r.amount);
  }

  const series = stack<Record<string, number>>()
    .keys(keys)
    .offset(stackOffsetWiggle)
    .order(stackOrderInsideOut)(table);
  const yMin = Math.min(...series.flatMap((s) => s.map((d) => d[0])));
  const yMax = Math.max(...series.flatMap((s) => s.map((d) => d[1])));
  const x = scaleTime()
    .domain([months[0] as Date, months[months.length - 1] as Date])
    .range([0, width]);
  const y = scaleLinear()
    .domain([yMin, yMax === yMin ? yMin + 1 : yMax])
    .range([height, 0]);
  const shape = area<[number, number] & { data: Record<string, number> }>()
    .x((d) => x(new Date(d.data["time"] as number)))
    .y0((d) => y(d[0]))
    .y1((d) => y(d[1]))
    .curve(curveBasis);

  const layers: StreamLayer[] = series.map((s) => ({
    group: s.key,
    colour: s.key === OTHER ? 5 : Math.min(keys.indexOf(s.key), 4),
    path: shape(s as unknown as ([number, number] & { data: Record<string, number> })[]) ?? "",
    totals: months.map((m, j) => ({ month: m, amount: table[j]?.[s.key] ?? 0 })),
  }));
  // Draw order from d3 is inside-out; `layers` keeps the key order for a stable legend.
  layers.sort((a, b) => keys.indexOf(a.group) - keys.indexOf(b.group));
  const monthTotals = table.map((cell) => keys.reduce((sum, k) => sum + (cell[k] ?? 0), 0));
  return { layers, months, kind, width, height, x: (m) => x(m), monthTotals };
}
