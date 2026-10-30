// The replay bundle's signed totals: a Merkle-sum tree root and a proof per agency.
// Nothing in the file is trusted until checkTotal has verified it in the browser.
import type { TotalProofJson } from "@/lib/verify/sumTree";

export interface BundleTotal {
  entity: string;
  agency: string | null;
  totalCents: bigint;
  count: number;
  proof: TotalProofJson;
}

export interface BundleTotals {
  treeSize: number;
  note: string;
  totals: BundleTotal[];
}

export function parseTotals(text: string): BundleTotals {
  const raw = JSON.parse(text) as {
    tree_size: number;
    note: string;
    totals: {
      entity: string;
      agency: string | null;
      total_cents: string;
      count: number;
      proof: TotalProofJson;
    }[];
  };
  return {
    treeSize: raw.tree_size,
    note: raw.note,
    totals: raw.totals.map((t) => ({
      entity: t.entity,
      agency: t.agency,
      totalCents: BigInt(t.total_cents),
      count: t.count,
      proof: t.proof,
    })),
  };
}

export async function loadTotals(base: string): Promise<BundleTotals | null> {
  const response = await fetch(`${base}/totals.json`);
  if (!response.ok) return null;
  return parseTotals(await response.text());
}
