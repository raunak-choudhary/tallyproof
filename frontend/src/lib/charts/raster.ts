/**
 * A raster plot of arrivals: one row per group, one tick per appended event, leaf index
 * along x. The ledger is a sequence, so bursts and gaps show the way spike trains do.
 * Pure layout; the component renders ticks on a canvas when there are many.
 */

import { scaleLinear } from "d3";

import type { LedgerRow } from "@/lib/ledger/events";

export interface RasterRow {
  group: string;
  y: number;
  count: number;
}

export interface RasterTick {
  x: number;
  y: number;
  row: number;
  eventId: string;
  leafIndex: number;
  /** True when the event is one of the highlighted set (a break's events, say). */
  marked: boolean;
}

export interface RasterLayout {
  rows: RasterRow[];
  ticks: RasterTick[];
  width: number;
  height: number;
  rowHeight: number;
  /** Leaf index range shown. */
  domain: [number, number];
}

export function rasterLayout(
  rows: readonly LedgerRow[],
  {
    width = 600,
    rowHeight = 14,
    maxRows = 12,
    marked = new Set<string>(),
    domain,
  }: {
    width?: number;
    rowHeight?: number;
    maxRows?: number;
    marked?: Set<string>;
    domain?: [number, number];
  } = {},
): RasterLayout {
  if (rows.length === 0)
    return { rows: [], ticks: [], width, height: 0, rowHeight, domain: [0, 1] };
  const counts = new Map<string, number>();
  for (const r of rows) counts.set(r.group, (counts.get(r.group) ?? 0) + 1);
  const ranked = [...counts.entries()].sort((a, b) => b[1] - a[1]);
  const named = ranked.slice(0, maxRows - (ranked.length > maxRows ? 1 : 0)).map(([g]) => g);
  const rowOf = new Map(named.map((g, i) => [g, i]));
  const otherRow = ranked.length > named.length ? named.length : -1;
  const rasterRows: RasterRow[] = named.map((g, i) => ({
    group: g,
    y: i * rowHeight + rowHeight / 2,
    count: counts.get(g) ?? 0,
  }));
  if (otherRow >= 0) {
    const rest = ranked.slice(named.length).reduce((s, [, n]) => s + n, 0);
    rasterRows.push({ group: "Other", y: otherRow * rowHeight + rowHeight / 2, count: rest });
  }
  const lo = domain?.[0] ?? Math.min(...rows.map((r) => r.leafIndex));
  const hi = domain?.[1] ?? Math.max(...rows.map((r) => r.leafIndex));
  const x = scaleLinear()
    .domain([lo, hi === lo ? lo + 1 : hi])
    .range([0, width]);
  const ticks: RasterTick[] = rows.map((r) => {
    const row = rowOf.get(r.group) ?? otherRow;
    return {
      x: x(r.leafIndex),
      y: row * rowHeight + rowHeight / 2,
      row,
      eventId: r.eventId,
      leafIndex: r.leafIndex,
      marked: marked.has(r.eventId),
    };
  });
  return {
    rows: rasterRows,
    ticks,
    width,
    height: rasterRows.length * rowHeight,
    rowHeight,
    domain: [lo, hi],
  };
}
