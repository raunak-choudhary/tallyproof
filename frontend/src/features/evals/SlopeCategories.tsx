"use client";

import { useId, useMemo, useState } from "react";

import { slopeLayout } from "@/lib/charts/evalCharts";
import type { CategoryRate } from "@/lib/evals/reports";
import { categoryLabel } from "@/lib/evals/reports";

const WIDTH = 420;
const HEIGHT = 240;
const LEFT = 120;
const RIGHT = WIDTH - 120;

// Per category, the share of questions that went as they should in one run against
// another. A rising line is a category that got better. Hover a line for the numbers.
export function SlopeCategories({
  left,
  right,
  leftLabel,
  rightLabel,
}: {
  left: readonly CategoryRate[];
  right: readonly CategoryRate[];
  leftLabel: string;
  rightLabel: string;
}) {
  const id = useId();
  const [hover, setHover] = useState<string | null>(null);
  const items = useMemo(() => {
    const keys = [...new Set([...left, ...right].map((c) => c.category))].sort();
    return keys.map((key) => ({
      key,
      left: left.find((c) => c.category === key)?.right ?? null,
      right: right.find((c) => c.category === key)?.right ?? null,
      n: right.find((c) => c.category === key)?.n ?? left.find((c) => c.category === key)?.n ?? 0,
    }));
  }, [left, right]);
  const layout = useMemo(() => slopeLayout(items, { width: WIDTH, height: HEIGHT }), [items]);
  const pct = (v: number | null) => (v === null ? "n/a" : `${Math.round(v * 100)}%`);

  return (
    <figure aria-labelledby={`${id}-t`} className="min-w-0">
      <figcaption id={`${id}-t`} className="text-sm font-medium">
        By category, one run against another
        <span className="block text-xs font-normal text-fg-muted">
          Share of each category&apos;s questions answered right or rightly refused
        </span>
      </figcaption>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT + 24}`}
        className="mt-2 block w-full"
        role="img"
        aria-label={`Slope chart, ${leftLabel} to ${rightLabel}: ${items
          .map((it) => `${categoryLabel(it.key)} ${pct(it.left)} to ${pct(it.right)}`)
          .join("; ")}`}
      >
        {[LEFT, RIGHT].map((x) => (
          <line key={x} x1={x} x2={x} y1={10} y2={HEIGHT - 10} stroke="var(--chart-grid)" />
        ))}
        {layout.lines.map((l, i) => {
          const it = items[i]!;
          const up = (l.change ?? 0) > 0.0001;
          const down = (l.change ?? 0) < -0.0001;
          const colour = up ? "var(--ok)" : down ? "var(--fail)" : "var(--fg-muted)";
          const faded = hover !== null && hover !== l.key;
          return (
            <g
              key={l.key}
              opacity={faded ? 0.25 : 1}
              style={{ transition: "opacity var(--dur-base)" }}
              onMouseEnter={() => setHover(l.key)}
              onMouseLeave={() => setHover(null)}
            >
              <title>{`${categoryLabel(l.key)} (${it.n} questions): ${pct(it.left)} to ${pct(it.right)}`}</title>
              {l.y1 !== null && l.y2 !== null && (
                <line x1={LEFT} x2={RIGHT} y1={l.y1} y2={l.y2} stroke={colour} strokeWidth="2.5" />
              )}
              {l.y1 !== null && <circle cx={LEFT} cy={l.y1} r="4" fill={colour} />}
              {l.y2 !== null && <circle cx={RIGHT} cy={l.y2} r="4" fill={colour} />}
              {l.ly1 !== null && (
                <text
                  x={LEFT - 8}
                  y={l.ly1 + 3}
                  textAnchor="end"
                  fontSize="10"
                  fill="var(--fg)"
                  fontFamily="var(--font-sans)"
                >
                  {categoryLabel(l.key)} {pct(it.left)}
                </text>
              )}
              {l.ly2 !== null && (
                <text
                  x={RIGHT + 8}
                  y={l.ly2 + 3}
                  fontSize="10"
                  fill="var(--fg)"
                  fontFamily="var(--font-sans)"
                >
                  {pct(it.right)} {categoryLabel(l.key)}
                </text>
              )}
            </g>
          );
        })}
        <text x={LEFT} y={HEIGHT + 16} textAnchor="middle" fontSize="10" fill="var(--fg-muted)">
          {leftLabel}
        </text>
        <text x={RIGHT} y={HEIGHT + 16} textAnchor="middle" fontSize="10" fill="var(--fg-muted)">
          {rightLabel}
        </text>
      </svg>
    </figure>
  );
}
