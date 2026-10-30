"use client";

import { useEffect, useId, useMemo, useState } from "react";

import { beeswarmLayout } from "@/lib/charts/beeswarm";
import type { CitedEvent } from "@/lib/analyst/api";
import { fetchEvent } from "@/lib/live/api";

const WIDTH = 640;
const RADIUS = 5;
const MAX = 200;
const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});
const exact = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

// The records behind one citation as a beeswarm on an amount axis. Amounts are read from
// the records the API served; they become proven only when a record is verified below, so
// the chart says so. Choose a dot to jump to that record and its Verify button.
export function CitationSwarm({ base, events }: { base: string; events: readonly CitedEvent[] }) {
  const id = useId();
  const [points, setPoints] = useState<{ id: string; amount: number }[] | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const shown = events.slice(0, MAX);

  useEffect(() => {
    let cancelled = false;
    void Promise.all(
      shown.map((e) =>
        fetchEvent(base, e.eventId)
          .then((ev) => {
            const amount = Number(
              (JSON.parse(ev.canonical) as { payload?: { amount?: unknown } }).payload?.amount,
            );
            return Number.isFinite(amount) ? { id: e.eventId, amount } : null;
          })
          .catch(() => null),
      ),
    ).then((rows) => {
      if (!cancelled) setPoints(rows.filter((r) => r !== null));
    });
    return () => {
      cancelled = true;
    };
    // The citation's records don't change for the life of this view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base]);

  const layout = useMemo(
    () => (points?.length ? beeswarmLayout(points, WIDTH, RADIUS) : null),
    [points],
  );
  if (!points) return <p className="mt-3 text-xs text-fg-muted">Reading the cited records…</p>;
  if (!layout) return null;
  const mid = layout.height / 2;
  const focus = layout.dots.find((d) => d.id === hover);
  const total = points.reduce((s, p) => s + p.amount, 0);
  const largest = Math.max(...points.map((p) => Math.abs(p.amount)));

  return (
    <figure aria-labelledby={`${id}-t`} className="mt-3 min-w-0">
      <figcaption id={`${id}-t`} className="text-xs text-fg-muted">
        {focus
          ? `${focus.id} · ${exact.format(focus.amount)}`
          : `${points.length.toLocaleString("en-US")} records by amount · the largest is ${Math.round(
              (largest / Math.max(1, Math.abs(total))) * 100,
            )}% of their sum · amounts as served, verify a record to prove it`}
      </figcaption>
      <svg
        viewBox={`0 0 ${WIDTH} ${layout.height + 18}`}
        className="mt-1 block w-full"
        role="img"
        aria-label={`Beeswarm of ${points.length} cited records by amount`}
      >
        <line x1={0} x2={WIDTH} y1={mid} y2={mid} stroke="var(--chart-grid)" />
        {layout.dots.map((d) => (
          <a key={d.id} href={`#rec-${d.id}`} aria-label={`${d.id}, ${exact.format(d.amount)}`}>
            <circle
              cx={d.x}
              cy={mid + d.y}
              r={d.id === hover ? RADIUS + 2 : RADIUS}
              fill={d.amount < 0 ? "var(--chart-3)" : "var(--chart-1)"}
              fillOpacity={hover && d.id !== hover ? 0.35 : 0.85}
              onMouseEnter={() => setHover(d.id)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(d.id)}
              onBlur={() => setHover(null)}
            />
          </a>
        ))}
        {layout.ticks.map((t) => (
          <text
            key={t.value}
            x={t.x}
            y={layout.height + 14}
            textAnchor={t.x < 30 ? "start" : t.x > WIDTH - 30 ? "end" : "middle"}
            fontSize="10"
            fill="var(--fg-muted)"
            fontFamily="var(--font-mono)"
          >
            {usd.format(t.value)}
          </text>
        ))}
      </svg>
    </figure>
  );
}
