import { describe, expect, it } from "vitest";

import type { EvalResult, RunSummary } from "@/lib/evals/reports";
import { bySystem, categoryRates, outcome, QUALITY_METRICS } from "@/lib/evals/reports";

import {
  brushed,
  dodge,
  horizonLayout,
  parallelLayout,
  questionMatrix,
  slopeLayout,
} from "./evalCharts";

function result(fields: Partial<EvalResult>): EvalResult {
  return {
    set: "smoke",
    id: "S001",
    question: "Total?",
    category: "numeric_aggregate",
    answerable: true,
    status: "answered",
    refusal: null,
    numeric_exact: true,
    must: 2,
    cited: 2,
    cited_correct: 2,
    cited_allowed: 2,
    policy_section_ok: null,
    quotes_faithful: null,
    injection_ok: null,
    integrity_ok: true,
    answer: "",
    tokens: 0,
    latency_ms: 0,
    ...fields,
  };
}

describe("question outcomes", () => {
  it("puts integrity before everything", () => {
    expect(outcome(result({ integrity_ok: false }))).toBe("integrity");
  });
  it("tells a right refusal from a wrong one", () => {
    expect(outcome(result({ status: "refused", answerable: false }))).toBe("refused");
    expect(outcome(result({ status: "refused" }))).toBe("wrong_refusal");
  });
  it("counts a wrong number or a missing citation as a miss", () => {
    expect(outcome(result({}))).toBe("right");
    expect(outcome(result({ numeric_exact: false }))).toBe("missed");
    expect(outcome(result({ cited_correct: 1 }))).toBe("missed");
    expect(outcome(result({ answerable: false }))).toBe("missed");
  });
  it("rates each category by questions that went as they should", () => {
    const rates = categoryRates([
      result({}),
      result({ id: "S002", numeric_exact: false }),
      result({ id: "S003", category: "refusal", answerable: false, status: "refused" }),
    ]);
    expect(rates).toEqual([
      { category: "numeric_aggregate", n: 2, right: 0.5 },
      { category: "refusal", n: 1, right: 1 },
    ]);
  });
});

describe("parallel coordinates", () => {
  const metrics = QUALITY_METRICS.slice(0, 3);
  const runs = [
    { id: "a", metrics: { numeric_exactness: 0.2, citation_precision: 0.5, citation_recall: 1 } },
    { id: "b", metrics: { numeric_exactness: 1, citation_precision: 1, citation_recall: null } },
  ];
  const layout = parallelLayout(
    runs,
    metrics,
    { numeric_exactness: 0.95 },
    {
      width: 300,
      height: 200,
    },
  );

  it("places one axis per metric and marks the gate where one exists", () => {
    expect(layout.axes.map((a) => a.key)).toEqual(metrics.map((m) => m.key));
    expect(layout.axes[0]!.gateY).toBeCloseTo(layout.y(0.95));
    expect(layout.axes[1]!.gateY).toBeNull();
  });
  it("sets the floor from the lowest value, rounded down to a tenth", () => {
    expect(layout.invert(layout.bottom)).toBeCloseTo(0.2);
    expect(layout.invert(layout.top)).toBeCloseTo(1);
  });
  it("breaks a run's line where a value is missing", () => {
    expect(layout.lines[1]!.path.match(/M/g)).toHaveLength(1);
    expect(layout.lines[1]!.path.split("L")).toHaveLength(2);
  });
  it("brushes runs inside every range and drops runs missing a brushed value", () => {
    expect(brushed(runs, { numeric_exactness: [0.9, 1] })).toEqual(new Set(["b"]));
    expect(brushed(runs, { citation_recall: [0, 1] })).toEqual(new Set(["a"]));
    expect(brushed(runs, {})).toEqual(new Set(["a", "b"]));
  });
});

describe("horizon charts", () => {
  it("draws only the bands the values reach, on the right side of the gate", () => {
    const h = horizonLayout([0.9, 1, 0.97], 0.95, { width: 100, height: 20 });
    const above = h.bands.filter((b) => b.sign === 1).map((b) => b.level);
    const below = h.bands.filter((b) => b.sign === -1).map((b) => b.level);
    expect(above).toEqual([0]);
    expect(below).toEqual([0]);
  });
  it("stacks a value far below the gate into every band", () => {
    const h = horizonLayout([0.2], 0.95, { width: 100, height: 20 });
    expect(h.bands.filter((b) => b.sign === -1)).toHaveLength(3);
  });
});

describe("slope chart", () => {
  it("keeps labels apart and in order", () => {
    const out = dodge([50, 52, 51, 10], 10, 0, 100);
    expect(out[3]).toBe(10);
    const sorted = [out[0]!, out[2]!, out[1]!];
    expect(sorted[1]! - sorted[0]!).toBeGreaterThanOrEqual(10);
    expect(sorted[2]! - sorted[1]!).toBeGreaterThanOrEqual(10);
  });
  it("pulls labels back inside the box", () => {
    const out = dodge([95, 96, 97], 10, 0, 100);
    expect(Math.max(...out)).toBeLessThanOrEqual(100);
  });
  it("reports each line's change", () => {
    const s = slopeLayout(
      [
        { key: "lookup", left: 0.5, right: 1 },
        { key: "policy", left: null, right: 0.3 },
      ],
      { width: 200, height: 200 },
    );
    expect(s.lines[0]!.change).toBe(0.5);
    expect(s.lines[1]!.change).toBeNull();
    expect(s.lines[1]!.y1).toBeNull();
  });
});

describe("question matrix", () => {
  it("lines questions up across runs and tells steady misses from flaky ones", () => {
    const rows = questionMatrix([
      { results: [result({ id: "S001", numeric_exact: false }), result({ id: "S002" })] },
      { results: [result({ id: "S001", numeric_exact: false }), result({ id: "S002", must: 3 })] },
      { results: [result({ id: "S002" })] },
    ]);
    expect(rows.map((r) => r.id)).toEqual(["S002", "S001"]);
    const [s2, s1] = rows;
    expect(s1!.cells.map((c) => c?.outcome ?? null)).toEqual(["missed", "missed", null]);
    expect(s1!.steady).toBe(true);
    expect(s1!.misses).toBe(2);
    expect(s2!.steady).toBe(false);
    expect(s2!.misses).toBe(1);
  });
});

describe("runs by system", () => {
  it("keeps the naive baseline out of the analyst's run history", () => {
    const run = (file: string, system?: string) => ({ file, system }) as unknown as RunSummary;
    const { analyst, naive } = bySystem([run("a"), run("b", "naive"), run("c", "analyst")]);
    expect(analyst.map((r) => r.file)).toEqual(["a", "c"]);
    expect(naive.map((r) => r.file)).toEqual(["b"]);
  });
});
