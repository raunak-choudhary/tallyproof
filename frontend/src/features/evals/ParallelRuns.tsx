"use client";

import { brushY, select } from "d3";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import type { ParallelRun } from "@/lib/charts/evalCharts";
import { brushed, parallelLayout } from "@/lib/charts/evalCharts";
import type { Metric } from "@/lib/evals/reports";

const WIDTH = 720;
const HEIGHT = 300;

// Every run across every quality metric, one line per run. Drag along an axis to keep
// only the runs inside that range (drag on several axes to combine); click a line, or a
// run in the list below, to open it. The dashed tick on each axis is its gate.
export function ParallelRuns({
  runs,
  metrics,
  gates,
  selected,
  labels,
  onSelect,
}: {
  runs: readonly ParallelRun[];
  metrics: readonly Metric[];
  gates: Record<string, number>;
  selected: string;
  labels: Record<string, string>;
  onSelect: (id: string) => void;
}) {
  const layout = useMemo(
    () => parallelLayout(runs, metrics, gates, { width: WIDTH, height: HEIGHT }),
    [runs, metrics, gates],
  );
  const [ranges, setRanges] = useState<Record<string, [number, number]>>({});
  const [hover, setHover] = useState<string | null>(null);
  const brushes = useRef<SVGGElement>(null);
  const id = useId();
  const kept = useMemo(() => brushed(runs, ranges), [runs, ranges]);

  useEffect(() => {
    const root = brushes.current;
    if (!root) return;
    const groups = select(root)
      .selectAll<SVGGElement, (typeof layout.axes)[number]>("g.axis-brush")
      .data(layout.axes, (d) => d.key)
      .join("g")
      .attr("class", "axis-brush");
    groups.each(function (axis) {
      const brush = brushY<unknown>()
        .extent([
          [axis.x - 12, layout.top],
          [axis.x + 12, layout.bottom],
        ])
        .on("brush end", (event: { selection: [number, number] | null }) => {
          setRanges((prev) => {
            const next = { ...prev };
            if (event.selection) {
              const [a, b] = event.selection;
              next[axis.key] = [layout.invert(b), layout.invert(a)];
            } else {
              delete next[axis.key];
            }
            return next;
          });
        });
      select(this).call(brush);
    });
    return () => {
      select(root).selectAll("g.axis-brush").remove();
    };
  }, [layout]);

  const active = Object.keys(ranges).length;
  return (
    <figure aria-labelledby={`${id}-t`} className="min-w-0">
      <figcaption id={`${id}-t`} className="text-sm font-medium">
        Every run, every metric
        <span className="block text-xs font-normal text-fg-muted">
          {active
            ? `${kept.size} of ${runs.length} runs inside the ranges you dragged`
            : "Drag along an axis to filter runs; the dashed tick is the gate"}
        </span>
      </figcaption>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="mt-2 block w-full touch-none select-none [&_.selection]:fill-[var(--accent)] [&_.selection]:fill-opacity-20 [&_.selection]:stroke-[var(--accent)]"
        role="img"
        aria-label={`Parallel coordinates: ${runs.length} runs across ${metrics.length} metrics`}
      >
        {layout.axes.map((axis) => (
          <g key={axis.key}>
            <line
              x1={axis.x}
              x2={axis.x}
              y1={layout.top}
              y2={layout.bottom}
              stroke="var(--chart-grid)"
              strokeWidth="2"
            />
            {axis.gateY !== null && (
              <line
                x1={axis.x - 9}
                x2={axis.x + 9}
                y1={axis.gateY}
                y2={axis.gateY}
                stroke="var(--fg-muted)"
                strokeDasharray="3 2"
                strokeWidth="1.5"
              />
            )}
            <text
              x={axis.x}
              y={layout.top - 12}
              textAnchor="middle"
              fontSize="11"
              fill="var(--fg-muted)"
              fontFamily="var(--font-sans)"
            >
              {axis.label}
            </text>
          </g>
        ))}
        {[layout.invert(layout.bottom), 1].map((v) => (
          <text
            key={v}
            x={layout.axes[0]!.x - 14}
            y={layout.y(v) + 3}
            textAnchor="end"
            fontSize="10"
            fill="var(--fg-muted)"
            fontFamily="var(--font-mono)"
          >
            {v.toFixed(1)}
          </text>
        ))}
        {layout.lines.map((l) => {
          const isSel = l.id === selected;
          const isHover = l.id === hover;
          const dim = !kept.has(l.id);
          return (
            <path
              key={l.id}
              d={l.path}
              fill="none"
              stroke={isSel ? "var(--accent)" : "var(--chart-2)"}
              strokeWidth={isSel || isHover ? 3 : 1.5}
              strokeOpacity={dim ? 0.08 : isSel || isHover ? 1 : 0.45}
              style={{ transition: "stroke-opacity var(--dur-base)", cursor: "pointer" }}
              onMouseEnter={() => setHover(l.id)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onSelect(l.id)}
            >
              <title>{labels[l.id]}</title>
            </path>
          );
        })}
        <g ref={brushes} />
      </svg>
      <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs" aria-label="Runs">
        {runs.map((r) => (
          <li key={r.id}>
            <button
              type="button"
              onClick={() => onSelect(r.id)}
              onMouseEnter={() => setHover(r.id)}
              onMouseLeave={() => setHover(null)}
              aria-pressed={r.id === selected}
              className={`rounded px-1 font-mono ${
                kept.has(r.id) ? "text-fg-muted" : "text-fg-muted/40"
              } hover:text-fg aria-pressed:font-semibold aria-pressed:text-accent`}
            >
              {labels[r.id]}
            </button>
          </li>
        ))}
      </ul>
    </figure>
  );
}
