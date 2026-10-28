import { readFileSync } from "node:fs";
import path from "node:path";

import { EventVerifier } from "@/features/event-verify/EventVerifier";

// The public site is a static export, so one page is generated per event in the bundle.
export const dynamicParams = false;

export function generateStaticParams(): { eventId: string }[] {
  const file = path.join(process.cwd(), "public", "replay", "events.jsonl");
  return readFileSync(file, "utf-8")
    .trim()
    .split("\n")
    .map((line) => ({ eventId: (JSON.parse(line) as { event_id: string }).event_id }));
}

export default async function EventPage({ params }: { params: Promise<{ eventId: string }> }) {
  const { eventId } = await params;
  return (
    <main className="mx-auto max-w-3xl px-4 py-12 md:px-8">
      <p className="text-sm text-fg-muted">Ledger event</p>
      <h1 className="mt-1 break-all font-mono text-xl md:text-2xl">{eventId}</h1>
      <div className="mt-8">
        <EventVerifier eventId={eventId} />
      </div>
    </main>
  );
}
