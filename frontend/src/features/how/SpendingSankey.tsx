"use client";

import { useId, useMemo, useState } from "react";

import type { FlowRow } from "@/lib/charts/sankey";
import { compactUsd, sankeyLayout } from "@/lib/charts/sankey";

const WIDTH = 640;
const HEIGHT = 340;
const usd = { format: compactUsd };

// The demo bundle's new obligations, from the agency that awarded them to the industry
// they bought from. Hover or focus a band to read it; the labels sit inside the chart.
export function SpendingSankey({ rows }: { rows: readonly FlowRow[] }) {
  const id = useId();
  const { nodes, links } = useMemo(
    () => sankeyLayout(rows, { width: WIDTH, height: HEIGHT }),
    [rows],
  );
  const [hover, setHover] = useState<number | null>(null);
  const total = links.reduce((s, l) => s + l.value, 0);
  const shown = hover === null ? null : links[hover]!;
  const name = (nid: string) => nid.slice(2);

  return (
    <figure aria-labelledby={`${id}-t`} className="min-w-0">
      <figcaption id={`${id}-t`} className="text-sm font-medium">
        Where the demo&apos;s money goes
        <span className="block text-xs font-normal text-fg-muted">
          {shown
            ? `${name(shown.source)} to ${name(shown.target)}: ${usd.format(shown.value)} (${Math.round((shown.value / total) * 100)}%)`
            : `${usd.format(total)} of new obligations in the signed bundle, awarding agency to industry`}
        </span>
      </figcaption>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="mt-2 block w-full"
        role="img"
        aria-label={`Sankey diagram: ${links
          .map((l) => `${name(l.source)} to ${name(l.target)} ${usd.format(l.value)}`)
          .join("; ")}`}
      >
        {links.map((l, i) => (
          <path
            key={`${l.source}-${l.target}`}
            d={l.path}
            fill="none"
            stroke={
              l.source.endsWith("Other")
                ? "var(--chart-6)"
                : `var(--chart-${(nodes.filter((n) => n.side === "agency").findIndex((n) => n.id === l.source) % 5) + 1})`
            }
            strokeOpacity={hover === null ? 0.45 : hover === i ? 0.85 : 0.12}
            strokeWidth={Math.max(1, l.width)}
            style={{ transition: "stroke-opacity var(--dur-base)" }}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          >
            <title>{`${name(l.source)} to ${name(l.target)}: ${usd.format(l.value)}`}</title>
          </path>
        ))}
        {nodes.map((n) => (
          <g key={n.id}>
            <rect
              x={n.x0}
              y={n.y0}
              width={n.x1 - n.x0}
              height={Math.max(1, n.y1 - n.y0)}
              fill="var(--fg-muted)"
              rx="2"
            />
            {n.y1 - n.y0 > 9 && (
              <text
                x={n.side === "agency" ? n.x1 + 6 : n.x0 - 6}
                y={(n.y0 + n.y1) / 2 + 4}
                textAnchor={n.side === "agency" ? "start" : "end"}
                fontSize="11"
                fill="var(--fg)"
                fontFamily="var(--font-sans)"
                paintOrder="stroke"
                stroke="var(--bg-elevated)"
                strokeWidth="3"
              >
                {n.name.replace(/^Department of (the )?/, "")}
              </text>
            )}
          </g>
        ))}
      </svg>
      <ol className="mt-3 grid gap-1 text-xs text-fg-muted" aria-label="Largest flows">
        {[...links]
          .sort((a, b) => b.value - a.value)
          .slice(0, 5)
          .map((l) => (
            <li key={`${l.source}-${l.target}`} className="flex justify-between gap-3">
              <span className="min-w-0">
                {name(l.source).replace(/^Department of (the )?/, "")} to {name(l.target)}
              </span>
              <span className="font-mono tabular-nums text-fg">{usd.format(l.value)}</span>
            </li>
          ))}
      </ol>
    </figure>
  );
}
