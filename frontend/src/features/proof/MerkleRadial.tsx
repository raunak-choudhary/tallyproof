"use client";

import { useEffect, useId, useMemo, useState } from "react";

import type { Climb, Placed } from "@/lib/charts/merkleClimb";
import { radialLayout } from "@/lib/charts/merkleClimb";
import { prefersReducedMotion } from "@/lib/motion";
import { equal } from "@/lib/verify/bytes";

const HOP_MS = 650;

// The audit path drawn as a radial tree: the leaf on the rim, the root at the centre,
// our path straight up, each sibling beside its partner. Every hash shown is one the
// verifier computed. The climb reveals one hop at a time; under reduced motion it is
// shown complete. Each node can take focus and names its hash for screen readers.
export function MerkleRadial({
  climbResult,
  signedRoot,
  title = "The audit path",
}: {
  climbResult: Climb;
  /** The root the signed checkpoint commits to, so the chart can show a match or a miss. */
  signedRoot: Uint8Array | null;
  title?: string;
}) {
  const layout = useMemo(() => radialLayout(climbResult, 400), [climbResult]);
  const total = climbResult.hops.length;
  const [shown, setShown] = useState(() => (prefersReducedMotion() ? total : 0));
  const headingId = useId();

  useEffect(() => {
    if (prefersReducedMotion()) return;
    const timer = window.setInterval(() => {
      setShown((n) => {
        if (n >= total) {
          window.clearInterval(timer);
          return n;
        }
        return n + 1;
      });
    }, HOP_MS);
    return () => window.clearInterval(timer);
  }, [total, climbResult]);

  const matches = signedRoot !== null && equal(climbResult.computedRoot, signedRoot);
  const done = shown >= total;
  const byId = new Map(layout.nodes.map((n) => [n.id, n]));
  // The leaf and its sibling show from the start; each later pair appears with its hop.
  const visible = (n: Placed) => n.role === "root" || n.hop < Math.max(shown, 1);
  const lit = (n: Placed) => (n.role === "root" ? done : n.hop < shown);

  const rootState = !done ? "pending" : matches ? "ok" : "fail";
  const rootColor =
    rootState === "ok" ? "var(--ok)" : rootState === "fail" ? "var(--fail)" : "var(--fg-muted)";

  return (
    <figure aria-labelledby={headingId} className="min-w-0">
      <figcaption id={headingId} className="text-sm font-medium">
        {title}
        <span className="block text-xs font-normal text-fg-muted">
          {total === 0
            ? "A single-leaf log: the leaf is the root."
            : `${shown} of ${total} hops${done ? (matches ? ": the root matches the signed checkpoint" : ": the root does not match the signed checkpoint") : ""}`}
        </span>
      </figcaption>
      <svg
        viewBox={`0 0 ${layout.size} ${layout.size}`}
        className="mx-auto mt-3 block w-full max-w-[440px]"
        role="list"
        aria-label="Nodes on the audit path, leaf first"
      >
        {layout.rings.map((r, k) =>
          r > 0 ? (
            <circle
              key={k}
              cx={layout.size / 2}
              cy={layout.size / 2}
              r={r}
              fill="none"
              stroke="var(--chart-grid)"
              strokeDasharray="2 5"
            />
          ) : null,
        )}
        {layout.edges.map((e) => {
          const a = byId.get(e.from);
          const b = byId.get(e.to);
          if (!a || !b) return null;
          const on = lit(a) && (b.role !== "root" || done || a.hop + 1 === shown);
          return (
            <line
              key={`${e.from}-${e.to}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke={on ? "var(--accent)" : "var(--border)"}
              strokeWidth={on ? 2 : 1}
              opacity={visible(a) ? 1 : 0.25}
              style={{ transition: "stroke var(--dur-base), opacity var(--dur-base)" }}
            />
          );
        })}
        {layout.nodes.map((n) => {
          const isLit = lit(n);
          const color = n.role === "root" ? rootColor : isLit ? "var(--accent)" : "var(--fg-muted)";
          const label =
            n.role === "root"
              ? `Root ${n.short}, ${rootState === "ok" ? "matches the signed checkpoint" : rootState === "fail" ? "does not match the signed checkpoint" : "not yet reached"}`
              : `${n.role === "self" ? "Our hash" : "Sibling"} at level ${n.level}: ${n.short}`;
          return (
            <g
              key={n.id}
              role="listitem"
              tabIndex={0}
              aria-label={label}
              className="outline-none focus-visible:[&>circle]:stroke-[3]"
              opacity={visible(n) ? 1 : 0.35}
              style={{ transition: "opacity var(--dur-base)" }}
            >
              <title>{n.hex}</title>
              <circle
                cx={n.x}
                cy={n.y}
                r={n.role === "root" ? 11 : n.role === "self" ? 8 : 6}
                fill={isLit || n.role === "root" ? "var(--bg-elevated)" : "var(--bg)"}
                stroke={color}
                strokeWidth={n.role === "sibling" ? 1.5 : 2.5}
                strokeDasharray={n.role === "sibling" ? "3 2" : undefined}
                style={{ transition: "stroke var(--dur-base), fill var(--dur-base)" }}
              />
              {(n.role !== "sibling" || (isLit && (layout.rings[n.level] ?? 0) > 70)) &&
                (() => {
                  // Labels sit outward along the radius, clear of the rings inside them.
                  const cx = layout.size / 2;
                  const dx = n.x - cx;
                  const dy = n.y - cx;
                  const d = Math.hypot(dx, dy) || 1;
                  const off = n.role === "root" ? 0 : n.role === "self" ? 13 : 10;
                  const lx = n.role === "root" ? cx : n.x + (dx / d) * off;
                  const ly = n.role === "root" ? n.y - 18 : n.y + (dy / d) * off + 3;
                  const anchor =
                    n.role === "root" || Math.abs(dx) < 6 ? "middle" : dx < 0 ? "end" : "start";
                  return (
                    <text
                      x={lx}
                      y={ly}
                      textAnchor={anchor}
                      fontSize={n.role === "sibling" ? "8.5" : "9.5"}
                      fontFamily="var(--font-mono)"
                      fill={isLit || n.role === "root" ? "var(--fg)" : "var(--fg-muted)"}
                    >
                      {n.short}
                    </text>
                  );
                })()}
            </g>
          );
        })}
      </svg>
      <ol className="sr-only">
        {climbResult.hops.map((h, k) => (
          <li key={k}>
            Level {k}: hash {layout.nodes.find((n) => n.id === `self-${k}`)?.short} with sibling{" "}
            {layout.nodes.find((n) => n.id === `sibling-${k}`)?.short} on the {h.siblingSide}.
          </li>
        ))}
      </ol>
    </figure>
  );
}
