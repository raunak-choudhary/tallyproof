"use client";

import { useId, useState } from "react";

import { horizonLayout } from "@/lib/charts/evalCharts";
import type { Metric } from "@/lib/evals/reports";

const WIDTH = 400;
const HEIGHT = 26;
const LEVELS = 3;

// One small horizon chart per metric, runs left to right. Each strip is the distance from
// the metric's gate folded into three bands of five points: violet above the gate, amber
// below, darker the further away. Hover or tap a strip for the run's value.
export function HorizonMetrics({
  metrics,
  gates,
  runs,
  selectedIndex,
  labels,
  onSelect,
}: {
  metrics: readonly Metric[];
  gates: Record<string, number>;
  runs: readonly { id: string; metrics: Record<string, number | null> }[];
  selectedIndex: number;
  labels: Record<string, string>;
  onSelect: (id: string) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const id = useId();
  const shown = hover ?? selectedIndex;
  const indexAt = (clientX: number, rect: DOMRect) =>
    Math.max(
      0,
      Math.min(
        runs.length - 1,
        Math.round(((clientX - rect.left) / rect.width) * (runs.length - 1)),
      ),
    );

  return (
    <figure aria-labelledby={`${id}-t`} className="min-w-0">
      <figcaption id={`${id}-t`} className="text-sm font-medium">
        Each metric over runs, against its gate
        <span className="block font-mono text-xs font-normal text-fg-muted">
          {labels[runs[shown]!.id]}
        </span>
      </figcaption>
      <dl className="mt-2 grid gap-1.5">
        {metrics.map((m) => {
          const gate = gates[m.key] ?? 1;
          const values = runs.map((r) => r.metrics[m.key] ?? null);
          const h = horizonLayout(values, gate, { width: WIDTH, height: HEIGHT }, LEVELS);
          const value = values[shown];
          const x = h.points[shown]!.x;
          return (
            <div
              key={m.key}
              className="grid grid-cols-[6.5rem_minmax(0,1fr)_3rem] items-center gap-2 sm:grid-cols-[9rem_minmax(0,1fr)_3.5rem]"
            >
              <dt className="truncate text-xs text-fg-muted" title={m.label}>
                {m.label}
              </dt>
              <dd className="min-w-0">
                <svg
                  viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
                  preserveAspectRatio="none"
                  className="block h-[26px] w-full cursor-crosshair rounded-sm bg-bg-sunken"
                  role="img"
                  aria-label={`${m.label}: ${values
                    .map((v) => (v === null ? "none" : v.toFixed(2)))
                    .join(", ")}; gate ${gate}`}
                  onMouseMove={(e) =>
                    setHover(indexAt(e.clientX, e.currentTarget.getBoundingClientRect()))
                  }
                  onMouseLeave={() => setHover(null)}
                  onClick={(e) =>
                    onSelect(runs[indexAt(e.clientX, e.currentTarget.getBoundingClientRect())]!.id)
                  }
                >
                  {h.bands.map((b) => (
                    <path
                      key={`${b.sign}${b.level}`}
                      d={b.path}
                      fill={b.sign === 1 ? "var(--chart-1)" : "var(--chart-3)"}
                      fillOpacity={0.3 + 0.25 * b.level}
                    />
                  ))}
                  <line
                    x1={x}
                    x2={x}
                    y1={0}
                    y2={HEIGHT}
                    stroke="var(--fg)"
                    strokeWidth="1.5"
                    vectorEffect="non-scaling-stroke"
                  />
                </svg>
              </dd>
              <dd
                className={`text-right font-mono text-xs tabular-nums ${
                  value !== null && value !== undefined && value < gate ? "text-warn" : "text-fg"
                }`}
              >
                {value === null || value === undefined ? "n/a" : value.toFixed(2)}
              </dd>
            </div>
          );
        })}
      </dl>
      <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-fg-muted">
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block size-2.5 rounded-sm bg-[var(--chart-1)]"
          />
          above the gate
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block size-2.5 rounded-sm bg-[var(--chart-3)]"
          />
          below the gate
        </span>
        <span>each shade is five points</span>
      </p>
    </figure>
  );
}
