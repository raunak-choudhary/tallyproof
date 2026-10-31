// Where a cited record and its proof come from. Live, the API serves both; on the
// static site, the signed replay bundle holds every record, and the proof is
// computed here from its leaves. Either way the browser verifies the result itself.
import type { LiveEvent, LiveProof } from "@/lib/live/api";
import { fetchEvent, fetchProof } from "@/lib/live/api";
import type { Bundle } from "@/lib/replay/bundle";
import { inclusionProof } from "@/lib/verify/merkle";

export interface RecordSource {
  event(eventId: string): Promise<LiveEvent>;
  proof(eventId: string, treeSize: number): Promise<LiveProof>;
}

export function apiRecords(base: string): RecordSource {
  return {
    event: (eventId) => fetchEvent(base, eventId),
    proof: (eventId, treeSize) => fetchProof(base, eventId, fetch, treeSize),
  };
}

export function bundleRecords(bundle: Bundle): RecordSource {
  const byId = new Map(bundle.records.map((r) => [r.eventId, r]));
  const find = (eventId: string) => {
    const record = byId.get(eventId);
    if (!record) throw new Error(`the bundle has no record ${eventId}`);
    return record;
  };
  return {
    event: (eventId) => {
      const record = find(eventId);
      const type = (JSON.parse(record.canonical) as { event_type: string }).event_type;
      return Promise.resolve({ ...record, eventType: type });
    },
    proof: (eventId, treeSize) => {
      const record = find(eventId);
      const checkpoint = bundle.checkpoints.find((c) => c.treeSize === treeSize);
      if (!checkpoint) throw new Error(`the bundle has no checkpoint at ${treeSize}`);
      return Promise.resolve({
        leafIndex: record.leafIndex,
        treeSize,
        auditPath: inclusionProof(bundle.leaves.slice(0, treeSize), record.leafIndex),
        checkpointNote: checkpoint.note,
      });
    },
  };
}
