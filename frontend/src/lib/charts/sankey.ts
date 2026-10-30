/**
 * Where the money goes: a Sankey from awarding agency to industry sector, links sized by
 * obligated amount. Small agencies and sectors fold into "Other" so the picture stays
 * readable at phone width. Pure layout over d3-sankey: rows in, positioned nodes and
 * link paths out.
 */

import { sankey, sankeyLinkHorizontal } from "d3-sankey";

export interface FlowRow {
  agency: string;
  sector: string;
  amount: number;
}

export interface SankeyNode {
  id: string;
  name: string;
  side: "agency" | "sector";
  value: number;
  x0: number;
  x1: number;
  y0: number;
  y1: number;
}

export interface SankeyLink {
  source: string;
  target: string;
  value: number;
  width: number;
  path: string;
}

export const OTHER = "Other";

/** The `limit` largest keys by total, the rest named OTHER. */
function keep(totals: Map<string, number>, limit: number): (key: string) => string {
  const top = new Set(
    [...totals.entries()]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, limit)
      .map(([k]) => k),
  );
  return (key) => (top.has(key) ? key : OTHER);
}

export function sankeyLayout(
  rows: readonly FlowRow[],
  box: { width: number; height: number },
  limits = { agencies: 5, sectors: 7 },
): { nodes: SankeyNode[]; links: SankeyLink[] } {
  const positive = rows.filter((r) => r.amount > 0);
  const sum = (key: (r: FlowRow) => string) => {
    const totals = new Map<string, number>();
    for (const r of positive) totals.set(key(r), (totals.get(key(r)) ?? 0) + r.amount);
    return totals;
  };
  const agency = keep(
    sum((r) => r.agency),
    limits.agencies,
  );
  const sector = keep(
    sum((r) => r.sector),
    limits.sectors,
  );
  const flows = new Map<string, number>();
  for (const r of positive) {
    const key = `a:${agency(r.agency)}\u0000s:${sector(r.sector)}`;
    flows.set(key, (flows.get(key) ?? 0) + r.amount);
  }
  const ids = new Set<string>();
  const links = [...flows.entries()].map(([key, value]) => {
    const [source, target] = key.split("\u0000") as [string, string];
    ids.add(source);
    ids.add(target);
    return { source, target, value };
  });
  const layout = sankey<{ id: string }, { source: string; target: string; value: number }>()
    .nodeId((n) => n.id)
    .nodeWidth(12)
    .nodePadding(10)
    .nodeSort((a, b) => (b.value ?? 0) - (a.value ?? 0))
    .extent([
      [1, 1],
      [box.width - 1, box.height - 1],
    ]);
  const graph = layout({
    nodes: [...ids].sort().map((id) => ({ id })),
    links: links.map((l) => ({ ...l })),
  });
  const path = sankeyLinkHorizontal();
  return {
    nodes: graph.nodes.map((n) => ({
      id: n.id,
      name: n.id.slice(2),
      side: n.id.startsWith("a:") ? "agency" : "sector",
      value: n.value ?? 0,
      x0: n.x0 ?? 0,
      x1: n.x1 ?? 0,
      y0: n.y0 ?? 0,
      y1: n.y1 ?? 0,
    })),
    links: graph.links.map((l) => ({
      source: (l.source as { id: string }).id,
      target: (l.target as { id: string }).id,
      value: l.value,
      width: l.width ?? 0,
      path: path(l) ?? "",
    })),
  };
}

/**
 * Dollars in compact form ($40.9M). Written out by hand rather than with Intl's compact
 * notation, which formats differently in Node and in browsers and so breaks hydration.
 */
export function compactUsd(value: number): string {
  const sign = value < 0 ? "-" : "";
  const v = Math.abs(value);
  const [div, unit] =
    v >= 1e9 ? [1e9, "B"] : v >= 1e6 ? [1e6, "M"] : v >= 1e3 ? [1e3, "K"] : [1, ""];
  const n = v / div;
  const text = unit
    ? (Math.round(n * 10) / 10).toFixed(n < 100 ? 1 : 0).replace(/\.0$/, "")
    : String(Math.round(n));
  return `${sign}$${text}${unit}`;
}

/** NAICS two-digit sectors, by the census bureau's names, shortened for labels. */
const SECTORS: Record<string, string> = {
  "11": "Agriculture",
  "21": "Mining and oil",
  "22": "Utilities",
  "23": "Construction",
  "31": "Manufacturing",
  "32": "Manufacturing",
  "33": "Manufacturing",
  "42": "Wholesale trade",
  "44": "Retail trade",
  "45": "Retail trade",
  "48": "Transportation",
  "49": "Transportation",
  "51": "Information",
  "52": "Finance and insurance",
  "53": "Real estate",
  "54": "Professional services",
  "55": "Management",
  "56": "Administrative support",
  "61": "Education",
  "62": "Health care",
  "71": "Arts and recreation",
  "72": "Accommodation and food",
  "81": "Other services",
  "92": "Public administration",
};

export function naicsSector(code: string | undefined | null): string {
  return (code && SECTORS[code.slice(0, 2)]) || "Unclassified";
}
