/**
 * A beeswarm of the records behind a total: one dot per record on an amount axis, nudged
 * up and down until no two overlap, so the reader sees whether a total is one large award
 * or many small ones. Amounts can be negative (deobligations) and span orders of
 * magnitude, so the axis is symmetric-log. Pure layout: the component only renders.
 */

import { scaleSymlog } from "d3";

export interface SwarmPoint {
  id: string;
  amount: number;
}

export interface SwarmDot extends SwarmPoint {
  x: number;
  /** Offset from the centre line; the component adds the centre. */
  y: number;
}

export interface SwarmLayout {
  dots: SwarmDot[];
  /** Height the dots need, centre line in the middle. */
  height: number;
  ticks: { value: number; x: number }[];
  x: (amount: number) => number;
}

/**
 * Place each dot as close to the centre line as it can go without touching a dot already
 * placed, trying above and below in turn. Larger amounts are placed first, so the big
 * records sit on the line. Deterministic: the same records always give the same picture.
 */
export function beeswarmLayout(
  points: readonly SwarmPoint[],
  width: number,
  radius = 4,
  padding = 1,
  minTickGap = 48,
): SwarmLayout {
  const amounts = points.map((p) => p.amount);
  const lo = Math.min(0, ...amounts);
  const hi = Math.max(0, ...amounts);
  const constant = Math.max(1, (Math.max(Math.abs(lo), Math.abs(hi)) || 1) / 1e4);
  const x = scaleSymlog()
    .constant(constant)
    .domain([lo, hi === lo ? lo + 1 : hi])
    .range([radius + 2, width - radius - 2])
    .nice();
  const gap = 2 * radius + padding;
  const order = [...points].sort(
    (a, b) => Math.abs(b.amount) - Math.abs(a.amount) || a.id.localeCompare(b.id),
  );
  const placed: SwarmDot[] = [];
  for (const p of order) {
    const px = x(p.amount);
    const near = placed.filter((d) => Math.abs(d.x - px) < gap);
    let y = 0;
    for (let k = 0; ; k++) {
      y = k === 0 ? 0 : (k % 2 === 1 ? 1 : -1) * Math.ceil(k / 2) * (gap / 2);
      if (near.every((d) => (d.x - px) ** 2 + (d.y - y) ** 2 >= gap * gap)) break;
    }
    placed.push({ ...p, x: px, y });
  }
  const extent = Math.max(0, ...placed.map((d) => Math.abs(d.y)));
  // Decade ticks (0, then 1k, 10k, 100k... each way), dropped where labels would crowd.
  const [d0, d1] = x.domain() as [number, number];
  const candidates = [0];
  for (let v = 1000; v <= Math.max(Math.abs(d0), Math.abs(d1)); v *= 10) {
    if (v <= d1) candidates.push(v);
    if (-v >= d0) candidates.push(-v);
  }
  const ticks: { value: number; x: number }[] = [];
  for (const value of candidates.sort((a, b) => Math.abs(a) - Math.abs(b))) {
    const at = x(value);
    if (ticks.every((t) => Math.abs(t.x - at) >= minTickGap)) ticks.push({ value, x: at });
  }
  ticks.sort((a, b) => a.x - b.x);
  return {
    dots: points.map((p) => placed.find((d) => d.id === p.id)!),
    height: 2 * (extent + radius + 2),
    ticks,
    x,
  };
}
