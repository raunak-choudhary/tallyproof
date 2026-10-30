import { readFileSync } from "node:fs";
import path from "node:path";

import { climb } from "@/lib/charts/merkleClimb";
import { toHex, utf8 } from "@/lib/verify/bytes";
import { parseCheckpoint } from "@/lib/verify/checkpoint";
import { leafHash } from "@/lib/verify/hashing";
import { inclusionProof } from "@/lib/verify/merkle";

import type { StoryData } from "./scenes/types";

// Computed at build time from the signed bundle in public/replay: the first obligation
// before the witnessed checkpoint, its leaf, its real audit path, and the real root.
export function storyData(): StoryData {
  const dir = path.join(process.cwd(), "public", "replay");
  const records = readFileSync(path.join(dir, "events.jsonl"), "utf-8")
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line) as { leaf_index: number; event_id: string; canonical: string });
  const checkpoints = readFileSync(path.join(dir, "checkpoints.jsonl"), "utf-8")
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line) as { tree_size: number; note: string });
  const latest = checkpoints.at(-1)!;
  const witnessed = checkpoints.filter((c) => c.tree_size < latest.tree_size).at(-1) ?? latest;
  const leaves = records.map((r) => leafHash(utf8(r.canonical)));
  const chosen =
    records.find(
      (r) => r.leaf_index < witnessed.tree_size && r.canonical.includes('"obligation.recorded"'),
    ) ?? records[0]!;
  const event = JSON.parse(chosen.canonical) as {
    payload: { awarding_agency?: string; piid?: string; amount: string; action_date: string };
  };
  const result = climb(
    leaves[chosen.leaf_index]!,
    chosen.leaf_index,
    leaves.length,
    inclusionProof(leaves, chosen.leaf_index),
  );
  const short = (h: Uint8Array) => `${toHex(h).slice(0, 6)}…${toHex(h).slice(-4)}`;
  return {
    record: {
      eventId: chosen.event_id,
      leafIndex: chosen.leaf_index,
      agency: event.payload.awarding_agency ?? "Contract modification",
      piid: event.payload.piid ?? "",
      amount: event.payload.amount,
      date: event.payload.action_date,
      canonical: JSON.stringify(JSON.parse(chosen.canonical), null, 2),
      leafHex: toHex(leaves[chosen.leaf_index]!),
    },
    treeSize: leaves.length,
    hops: result.hops.map((h) => ({
      self: short(h.self),
      sibling: short(h.sibling),
      parent: short(h.parent),
      side: h.siblingSide,
    })),
    rootHex: toHex(parseCheckpoint(`${latest.note.split("\n\n")[0]}\n`).rootHash),
    checkpointNote: latest.note,
    witnessedSize: witnessed.tree_size,
  };
}
