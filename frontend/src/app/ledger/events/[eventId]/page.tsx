import { readFileSync } from "node:fs";
import path from "node:path";

import { EventVerifier } from "@/features/event-verify/EventVerifier";
import type { Displayed } from "@/lib/verify/verifyEvent";

// The public site is a static export, so one page is generated per event in the bundle.
export const dynamicParams = false;

function bundleLines(): { event_id: string; canonical: string }[] {
  const file = path.join(process.cwd(), "public", "replay", "events.jsonl");
  return readFileSync(file, "utf-8")
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line) as { event_id: string; canonical: string });
}

export function generateStaticParams(): { eventId: string }[] {
  return bundleLines().map((line) => ({ eventId: line.event_id }));
}

// The values this page prints are written into its HTML at build time. The verifier then
// checks each one against the bytes it verified, so a page altered after publishing (or
// a summary that drifted from its record) shows as a failure, not as a green check.
function displayedValues(eventId: string): Displayed[] {
  const line = bundleLines().find((l) => l.event_id === eventId);
  if (!line) return [];
  const record = JSON.parse(line.canonical) as {
    event_type: string;
    payload: Record<string, unknown>;
  };
  const fields: [string, string[]][] = [
    ["Type", ["event_type"]],
    ["Agency", ["payload", "awarding_agency"]],
    ["Amount", ["payload", "amount"]],
    ["Date", ["payload", "action_date"]],
  ];
  return fields.flatMap(([label, at]) => {
    let value: unknown = record;
    for (const key of at) value = (value as Record<string, unknown> | undefined)?.[key];
    return value === undefined || value === null ? [] : [{ label, path: at, value: String(value) }];
  });
}

export default async function EventPage({ params }: { params: Promise<{ eventId: string }> }) {
  const { eventId } = await params;
  const displayed = displayedValues(eventId);
  return (
    <main className="mx-auto max-w-3xl px-4 py-12 md:px-8">
      <p className="text-sm text-fg-muted">Ledger event</p>
      <h1 className="mt-1 break-all font-mono text-xl md:text-2xl">{eventId}</h1>
      {displayed.length > 0 && (
        <dl className="mt-6 grid grid-cols-2 gap-4 rounded-[var(--radius)] border border-border bg-bg-elevated p-4 sm:grid-cols-4">
          {displayed.map((d) => (
            <div key={d.label} className="min-w-0">
              <dt className="text-xs text-fg-muted">{d.label}</dt>
              <dd className="breakable font-mono text-sm">{d.value}</dd>
            </div>
          ))}
        </dl>
      )}
      <div className="mt-8">
        <EventVerifier eventId={eventId} displayed={displayed} />
      </div>
    </main>
  );
}
