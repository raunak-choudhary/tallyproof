/**
 * The ledger as the charts see it: one row per event with the fields the ledger page
 * reads, taken from the record's canonical bytes (what the proof covers), never from a
 * separate summary.
 */

export interface LedgerRow {
  eventId: string;
  leafIndex: number;
  eventType: string;
  /** The event's own date: action date for obligations, record date for cash, else emitted. */
  date: Date;
  /** Awarding agency for obligations; "Modification" for adjustments; the account otherwise. */
  group: string;
  /** Signed amount in dollars, or 0 for events without one. */
  amount: number;
}

interface CanonicalEvent {
  event_id: string;
  event_type: string;
  emitted_at: string;
  payload: Record<string, unknown>;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/** Parse one canonical record into a row. Returns null if the bytes aren't a ledger event. */
export function rowFromCanonical(canonical: string, leafIndex: number): LedgerRow | null {
  let event: CanonicalEvent;
  try {
    event = JSON.parse(canonical) as CanonicalEvent;
  } catch {
    return null;
  }
  if (typeof event?.event_id !== "string" || typeof event.payload !== "object" || !event.payload)
    return null;
  const p = event.payload;
  const dateText =
    text(p["action_date"]) ?? text(p["record_date"]) ?? text(event.emitted_at) ?? null;
  const date = dateText ? new Date(dateText) : new Date(NaN);
  if (Number.isNaN(date.getTime())) return null;
  const amountText = text(p["amount"]) ?? text(p["period_outlay"]) ?? "0";
  const amount = Number(amountText);
  const group =
    text(p["awarding_agency"]) ??
    (event.event_type === "obligation.adjusted" ? "Modification" : null) ??
    text(p["account"]) ??
    text(p["treasury_account"]) ??
    event.event_type;
  return {
    eventId: event.event_id,
    leafIndex,
    eventType: event.event_type,
    date,
    group,
    amount: Number.isFinite(amount) ? amount : 0,
  };
}

/** Rows from the demo bundle's records, in leaf order. */
export function rowsFromRecords(
  records: readonly { canonical: string; leafIndex: number }[],
): LedgerRow[] {
  const rows: LedgerRow[] = [];
  for (const r of records) {
    const row = rowFromCanonical(r.canonical, r.leafIndex);
    if (row) rows.push(row);
  }
  return rows.sort((a, b) => a.leafIndex - b.leafIndex);
}
