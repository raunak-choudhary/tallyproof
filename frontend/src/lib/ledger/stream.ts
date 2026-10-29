/**
 * The live stream of ledger facts over the WebSocket at /ws/v1/stream: appended events,
 * signed checkpoints, breaks found, and a note when the client fell behind. No polling.
 * Reconnects with backoff; the caller re-reads state over REST after a drop.
 */

export type Fact =
  | { kind: "event_appended"; event_id: string; leaf_index: number }
  | { kind: "checkpoint_signed"; tree_size: number }
  | { kind: "break_found"; break_id: string }
  | { kind: "facts_dropped"; count: number };

const KINDS = new Set(["event_appended", "checkpoint_signed", "break_found", "facts_dropped"]);

/** Parse one frame; anything that isn't a known fact is ignored. */
export function parseFact(text: string): Fact | null {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return null;
  }
  if (typeof data !== "object" || data === null) return null;
  const kind = (data as { kind?: unknown }).kind;
  if (typeof kind !== "string" || !KINDS.has(kind)) return null;
  return data as Fact;
}

/** The stream URL for a WebSocket base such as ws://127.0.0.1:8001. */
export function streamUrl(base: string): string {
  return `${base.replace(/\/+$/, "")}/ws/v1/stream`;
}

export interface StreamHandle {
  close: () => void;
}

interface SocketLike {
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev: unknown) => void) | null;
  onerror: ((ev: unknown) => void) | null;
  close: () => void;
}

/**
 * Open the stream and call `onFact` for every fact. Reconnects after a drop, waiting 1,
 * 2, 4, up to 30 seconds. `connect` is injectable so tests use a fake socket.
 */
export function openStream(
  url: string,
  onFact: (fact: Fact) => void,
  {
    onStatus = () => {},
    connect = (u: string) => new WebSocket(u) as unknown as SocketLike,
    schedule = (fn: () => void, ms: number) => setTimeout(fn, ms) as unknown as number,
    cancel = (id: number) => clearTimeout(id),
  }: {
    onStatus?: (status: "connecting" | "open" | "closed") => void;
    connect?: (url: string) => SocketLike;
    schedule?: (fn: () => void, ms: number) => number;
    cancel?: (id: number) => void;
  } = {},
): StreamHandle {
  let socket: SocketLike | null = null;
  let closed = false;
  let delay = 1000;
  let timer: number | null = null;

  const open = () => {
    if (closed) return;
    onStatus("connecting");
    socket = connect(url);
    socket.onopen = () => {
      delay = 1000;
      onStatus("open");
    };
    socket.onmessage = (ev) => {
      if (typeof ev.data !== "string") return;
      const fact = parseFact(ev.data);
      if (fact) onFact(fact);
    };
    socket.onerror = () => {};
    socket.onclose = () => {
      onStatus("closed");
      if (closed) return;
      timer = schedule(open, delay);
      delay = Math.min(delay * 2, 30_000);
    };
  };
  open();
  return {
    close: () => {
      closed = true;
      if (timer !== null) cancel(timer);
      socket?.close();
    },
  };
}
