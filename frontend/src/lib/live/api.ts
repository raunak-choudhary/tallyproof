// A small client for the live proof API. It returns what the API sent; deciding
// whether any of it is true is the verifier's job, not this module's.
import { fromHex } from "@/lib/verify/bytes";

export interface LiveEvent {
  eventId: string;
  leafIndex: number;
  eventType: string;
  canonical: string;
}

export interface LiveProof {
  leafIndex: number;
  treeSize: number;
  auditPath: Uint8Array[];
  checkpointNote: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** The API base URL compiled into the build, or null when live mode is off. */
export function apiBase(): string | null {
  const base = process.env.NEXT_PUBLIC_API_URL;
  return base ? base.replace(/\/+$/, "") : null;
}

async function getJson(base: string, path: string, fetcher: typeof fetch): Promise<unknown> {
  const response = await fetcher(`${base}${path}`, { headers: { Accept: "application/json" } });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body ? String(body.detail) : "";
    throw new ApiError(detail || `the API answered ${response.status}`, response.status);
  }
  return body;
}

interface RawEvent {
  event_id: string;
  leaf_index: number;
  event_type: string;
  canonical: string;
}

function toEvent(raw: RawEvent): LiveEvent {
  return {
    eventId: raw.event_id,
    leafIndex: raw.leaf_index,
    eventType: raw.event_type,
    canonical: raw.canonical,
  };
}

export async function recentEvents(
  base: string,
  limit = 20,
  fetcher: typeof fetch = fetch,
): Promise<LiveEvent[]> {
  const body = (await getJson(base, `/api/v1/events?limit=${limit}`, fetcher)) as {
    results: RawEvent[];
  };
  return body.results.map(toEvent);
}

export async function fetchEvent(
  base: string,
  eventId: string,
  fetcher: typeof fetch = fetch,
): Promise<LiveEvent> {
  const id = encodeURIComponent(eventId);
  return toEvent((await getJson(base, `/api/v1/events/${id}`, fetcher)) as RawEvent);
}

export async function fetchProof(
  base: string,
  eventId: string,
  fetcher: typeof fetch = fetch,
): Promise<LiveProof> {
  const id = encodeURIComponent(eventId);
  const body = (await getJson(base, `/api/v1/events/${id}/proof`, fetcher)) as {
    leaf_index: number;
    tree_size: number;
    audit_path_hex: string[];
    checkpoint_note: string;
  };
  return {
    leafIndex: body.leaf_index,
    treeSize: body.tree_size,
    auditPath: body.audit_path_hex.map(fromHex),
    checkpointNote: body.checkpoint_note,
  };
}
