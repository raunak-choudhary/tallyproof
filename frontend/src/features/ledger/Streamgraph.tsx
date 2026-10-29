"use client";

import { useId, useMemo, useState } from "react";

import { streamgraphLayout } from "@/lib/charts/streamgraph";
import type { LedgerRow } from "@/lib/ledger/events";

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});
const monthName = new Intl.DateTimeFormat("en-US", {
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});
const dayName = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

// Amounts over time by group as a streamgraph. Hover or focus a month to read every
// group's total; click a layer to isolate it. Scales with its container (viewBox).
export function Streamgraph({
  rows,
  title = "Obligations over time, by awarding agency",
  onPickMonth,
}: {
  rows: readonly LedgerRow[];
  title?: string;
  /** Called with the month the reader chose, so the page can list its records. */
  onPickMonth?: (month: Date) => void;
}) {
  const width = 640;
  const height = 220;
  const layout = useMemo(() => streamgraphLayout(rows, { width, height }), [rows]);
  const [hover, setHover] = useState<number | null>(null);
  const [only, setOnly] = useState<string | null>(null);
  const id = useId();

  if (layout.layers.length === 0) {
    return <p className="text-sm text-fg-muted">No amounts to chart yet.</p>;
  }
  const monthAt = (clientX: number, rect: DOMRect) => {
    const x = ((clientX - rect.left) / rect.width) * width;
    let best = 0;
    layout.months.forEach((m, i) => {
      if (Math.abs(layout.x(m) - x) < Math.abs(layout.x(layout.months[best]!) - x)) best = i;
    });
    return best;
  };
  const shown = hover ?? layout.months.length - 1;
  const month = layout.months[shown]!;
  const name = (m: Date) =>
    layout.kind === "month"
      ? monthName.format(m)
      : layout.kind === "day"
        ? dayName.format(m)
        : `leaf ${m.getTime().toLocaleString("en-US")}`;
  const unit =
    layout.kind === "month" ? "month" : layout.kind === "day" ? "day" : "stretch of the log";

  return (
    <figure aria-labelledby={`${id}-t`} className="min-w-0">
      <figcaption id={`${id}-t`} className="text-sm font-medium">
        {title}
        <span className="block font-mono text-xs font-normal text-fg-muted">
          {name(month)} · {usd.format(layout.monthTotals[shown] ?? 0)} across {layout.layers.length}{" "}
          groups · by {unit}
        </span>
      </figcaption>
      <svg
        viewBox={`0 0 ${width} ${height + 24}`}
        className="mt-2 block w-full"
        role="img"
        aria-label={`${title}: ${layout.months.length} bins by ${unit}, ${layout.layers.length} groups`}
        onMouseMove={(e) => setHover(monthAt(e.clientX, e.currentTarget.getBoundingClientRect()))}
        onMouseLeave={() => setHover(null)}
        onTouchStart={(e) => {
          const t = e.touches[0];
          if (t) setHover(monthAt(t.clientX, e.currentTarget.getBoundingClientRect()));
        }}
        onClick={() => onPickMonth?.(month)}
      >
        {layout.layers.map((layer) => (
          <path
            key={layer.group}
            d={layer.path}
            fill={`var(--chart-${layer.colour + 1})`}
            opacity={only === null || only === layer.group ? 0.92 : 0.18}
            style={{ transition: "opacity var(--dur-base)" }}
            onClick={(e) => {
              e.stopPropagation();
              setOnly(only === layer.group ? null : layer.group);
            }}
          >
            <title>{layer.group}</title>
          </path>
        ))}
        <line
          x1={layout.x(month)}
          x2={layout.x(month)}
          y1={0}
          y2={height}
          stroke="var(--fg)"
          strokeOpacity={0.5}
          strokeDasharray="3 3"
        />
        {layout.months
          .filter((_, i) => i % Math.max(1, Math.floor(layout.months.length / 6)) === 0)
          .map((m) => (
            <text
              key={m.getTime()}
              x={layout.x(m)}
              y={height + 16}
              fontSize="10"
              fontFamily="var(--font-sans)"
              fill="var(--fg-muted)"
              textAnchor={layout.x(m) < 20 ? "start" : layout.x(m) > width - 20 ? "end" : "middle"}
            >
              {name(m)}
            </text>
          ))}
      </svg>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-muted" aria-label="Groups">
        {layout.layers.map((layer) => (
          <li key={layer.group}>
            <button
              type="button"
              onClick={() => setOnly(only === layer.group ? null : layer.group)}
              aria-pressed={only === layer.group}
              className="inline-flex items-center gap-1.5 rounded px-1 hover:text-fg aria-pressed:font-medium aria-pressed:text-fg"
            >
              <span
                aria-hidden="true"
                className="inline-block size-2.5 rounded-sm"
                style={{ background: `var(--chart-${layer.colour + 1})` }}
              />
              {layer.group}
              <span className="font-mono tabular-nums">
                {usd.format(layer.totals[shown]?.amount ?? 0)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </figure>
  );
}
