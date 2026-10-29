"use client";

import Link from "next/link";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { rasterLayout } from "@/lib/charts/raster";
import type { LedgerRow } from "@/lib/ledger/events";

// Arrivals as a raster plot: a row per group, a tick per appended event, leaf index along
// x, the way a spike raster shows a neuron's firing. Ticks are drawn on a canvas, since
// there can be thousands; the row list beside it is the accessible summary, and the
// nearest tick to the pointer is named and linked.
export function ArrivalRaster({
  rows,
  marked = new Set<string>(),
  title = "Arrivals, by group",
}: {
  rows: readonly LedgerRow[];
  /** Event IDs to draw in the attention colour (a break's events). */
  marked?: Set<string>;
  title?: string;
}) {
  const width = 640;
  const layout = useMemo(() => rasterLayout(rows, { width, marked }), [rows, marked]);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [near, setNear] = useState<{ eventId: string; leafIndex: number; group: string } | null>(
    null,
  );
  const id = useId();

  useEffect(() => {
    const el = canvas.current;
    if (!el || layout.height === 0) return;
    const scale = window.devicePixelRatio || 1;
    el.width = width * scale;
    el.height = layout.height * scale;
    const ctx = el.getContext("2d");
    if (!ctx) return;
    const styles = getComputedStyle(el);
    const tick = styles.getPropertyValue("--chart-2").trim() || "#22d3ee";
    const warn = styles.getPropertyValue("--warn").trim() || "#f5b82e";
    const grid = styles.getPropertyValue("--chart-grid").trim() || "#333";
    ctx.scale(scale, scale);
    ctx.clearRect(0, 0, width, layout.height);
    ctx.strokeStyle = grid;
    ctx.lineWidth = 1;
    layout.rows.forEach((r, i) => {
      if (i === 0) return;
      ctx.beginPath();
      ctx.moveTo(0, i * layout.rowHeight + 0.5);
      ctx.lineTo(width, i * layout.rowHeight + 0.5);
      ctx.stroke();
    });
    ctx.lineWidth = 1;
    for (const t of layout.ticks) {
      ctx.strokeStyle = t.marked ? warn : tick;
      ctx.globalAlpha = t.marked ? 1 : 0.8;
      ctx.beginPath();
      ctx.moveTo(t.x + 0.5, t.y - layout.rowHeight / 2 + 2);
      ctx.lineTo(t.x + 0.5, t.y + layout.rowHeight / 2 - 2);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }, [layout]);

  if (layout.height === 0) return <p className="text-sm text-fg-muted">No arrivals yet.</p>;

  const pick = (clientX: number, clientY: number, rect: DOMRect) => {
    const x = ((clientX - rect.left) / rect.width) * width;
    const y = ((clientY - rect.top) / rect.height) * layout.height;
    const row = Math.floor(y / layout.rowHeight);
    let best: (typeof layout.ticks)[number] | null = null;
    for (const t of layout.ticks) {
      if (t.row !== row) continue;
      if (!best || Math.abs(t.x - x) < Math.abs(best.x - x)) best = t;
    }
    setNear(
      best
        ? { eventId: best.eventId, leafIndex: best.leafIndex, group: layout.rows[row]?.group ?? "" }
        : null,
    );
  };

  return (
    <figure aria-labelledby={`${id}-t`} className="min-w-0">
      <figcaption id={`${id}-t`} className="text-sm font-medium">
        {title}
        <span className="block font-mono text-xs font-normal text-fg-muted">
          leaves {layout.domain[0].toLocaleString("en-US")} to{" "}
          {layout.domain[1].toLocaleString("en-US")} · {layout.ticks.length.toLocaleString("en-US")}{" "}
          events
        </span>
      </figcaption>
      <div className="mt-2 grid grid-cols-[auto_1fr] gap-2">
        <ul className="text-xs text-fg-muted" aria-label="Rows">
          {layout.rows.map((r) => (
            <li
              key={r.group}
              style={{ height: layout.rowHeight, lineHeight: `${layout.rowHeight}px` }}
              className="max-w-[9rem] truncate"
              title={`${r.group}: ${r.count} events`}
            >
              {r.group}
            </li>
          ))}
        </ul>
        <canvas
          ref={canvas}
          style={{ width: "100%", height: layout.height }}
          className="block min-w-0 rounded-sm bg-bg-sunken"
          role="img"
          aria-label={`${layout.ticks.length} events across ${layout.rows.length} rows`}
          onMouseMove={(e) => pick(e.clientX, e.clientY, e.currentTarget.getBoundingClientRect())}
          onTouchStart={(e) => {
            const t = e.touches[0];
            if (t) pick(t.clientX, t.clientY, e.currentTarget.getBoundingClientRect());
          }}
        />
      </div>
      <p className="mt-2 min-h-5 font-mono text-xs text-fg-muted" aria-live="polite">
        {near ? (
          <>
            {near.group} · leaf {near.leafIndex} ·{" "}
            <Link href={`/ledger/events/${near.eventId}/`} className="text-accent hover:underline">
              {near.eventId}
            </Link>
          </>
        ) : (
          "Hover or tap a tick to name its event."
        )}
      </p>
    </figure>
  );
}
