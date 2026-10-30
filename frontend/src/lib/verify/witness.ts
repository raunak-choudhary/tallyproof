// The outside witness: a checkpoint published somewhere other than the site that serves
// the bundle, so a server that rewrites its history can't also rewrite what was witnessed.
// The page fetches it, then the verifier checks its signature and a consistency proof.

/** Where the witnessed checkpoint is published, compiled into the build; null when unset. */
export function witnessUrl(): string | null {
  return process.env.NEXT_PUBLIC_WITNESS_URL || null;
}

/** The newest checkpoint note in a witness export (one JSON object per line). */
export function latestWitnessed(text: string): { treeSize: number; note: string } | null {
  let latest: { treeSize: number; note: string } | null = null;
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    const record = JSON.parse(line) as { tree_size?: unknown; note?: unknown };
    if (typeof record.tree_size !== "number" || typeof record.note !== "string") continue;
    if (!latest || record.tree_size > latest.treeSize)
      latest = { treeSize: record.tree_size, note: record.note };
  }
  return latest;
}

export type FetchedWitness = { note: string; source: string } | { error: string; source: string };

export async function fetchWitness(
  url: string,
  fetcher: typeof fetch = fetch,
): Promise<FetchedWitness> {
  const source = new URL(url).host;
  try {
    const response = await fetcher(url, { cache: "no-store" });
    if (!response.ok) return { error: `it answered ${response.status}`, source };
    const latest = latestWitnessed(await response.text());
    return latest
      ? { note: latest.note, source }
      : { error: "the file holds no checkpoint", source };
  } catch (error) {
    return { error: error instanceof Error ? error.message : String(error), source };
  }
}
