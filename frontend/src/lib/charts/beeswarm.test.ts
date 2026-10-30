import { describe, expect, it } from "vitest";

import { beeswarmLayout } from "./beeswarm";

describe("beeswarm", () => {
  const points = [
    { id: "big", amount: 1_000_000 },
    ...Array.from({ length: 12 }, (_, i) => ({ id: `s${i}`, amount: 100 + i })),
    { id: "neg", amount: -5_000 },
  ];
  const layout = beeswarmLayout(points, 400, 4);

  it("keeps every dot apart", () => {
    for (const a of layout.dots)
      for (const b of layout.dots)
        if (a !== b) expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThanOrEqual(8.999);
  });

  it("puts the largest record on the centre line and orders the axis by amount", () => {
    const big = layout.dots.find((d) => d.id === "big")!;
    expect(big.y).toBe(0);
    const neg = layout.dots.find((d) => d.id === "neg")!;
    expect(neg.x).toBeLessThan(layout.dots.find((d) => d.id === "s0")!.x);
    expect(big.x).toBeGreaterThan(layout.dots.find((d) => d.id === "s0")!.x);
  });

  it("keeps the input order and stays inside the width", () => {
    expect(layout.dots.map((d) => d.id)).toEqual(points.map((p) => p.id));
    for (const d of layout.dots) {
      expect(d.x).toBeGreaterThanOrEqual(0);
      expect(d.x).toBeLessThanOrEqual(400);
    }
    expect(layout.height).toBeGreaterThan(8);
  });

  it("labels decades both ways without crowding", () => {
    const values = layout.ticks.map((t) => t.value);
    expect(values).toContain(0);
    expect(values.some((v) => v < 0)).toBe(true);
    for (let i = 1; i < layout.ticks.length; i++)
      expect(layout.ticks[i]!.x - layout.ticks[i - 1]!.x).toBeGreaterThanOrEqual(48);
  });

  it("is deterministic and handles one record", () => {
    expect(beeswarmLayout(points, 400, 4).dots).toEqual(layout.dots);
    expect(beeswarmLayout([{ id: "a", amount: 5 }], 200).dots[0]!.y).toBe(0);
  });
});
