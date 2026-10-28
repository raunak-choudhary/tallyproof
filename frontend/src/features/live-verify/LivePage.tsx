"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import type { LiveEvent } from "@/lib/live/api";
import { apiBase, recentEvents } from "@/lib/live/api";

import { LiveEventVerifier } from "./LiveEventVerifier";

function RecentEvents({ base }: { base: string }) {
  const [events, setEvents] = useState<LiveEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    recentEvents(base)
      .then(setEvents)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [base]);

  if (error) {
    return (
      <p role="alert" className="text-fail">
        Could not reach the live API: {error}
      </p>
    );
  }
  if (!events) return <p className="text-fg-muted">Loading recent events…</p>;
  if (events.length === 0) return <p className="text-fg-muted">The live ledger is empty so far.</p>;
  return (
    <ul className="divide-y divide-border rounded-[var(--radius)] border border-border">
      {events.map((event) => (
        <li key={event.eventId}>
          <Link
            href={`/live/?id=${encodeURIComponent(event.eventId)}`}
            className="flex flex-col gap-1 px-4 py-3 hover:bg-bg-elevated focus-visible:outline-2 focus-visible:outline-accent sm:flex-row sm:justify-between"
          >
            <span className="break-all font-mono text-sm">{event.eventId}</span>
            <span className="text-sm text-fg-muted">
              leaf {event.leafIndex} · {event.eventType}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function LivePage() {
  const base = apiBase();
  const eventId = useSearchParams().get("id");

  if (!base) {
    return (
      <p className="text-fg-muted">
        Live mode is off in this build. Set NEXT_PUBLIC_API_URL to a running Tallyproof API to use
        it.
      </p>
    );
  }
  if (eventId) {
    return (
      <>
        <h1 className="break-all font-mono text-xl md:text-2xl">{eventId}</h1>
        <div className="mt-8">
          <LiveEventVerifier base={base} eventId={eventId} />
        </div>
      </>
    );
  }
  return (
    <>
      <h1 className="text-2xl font-semibold md:text-3xl">Live ledger</h1>
      <p className="mt-2 text-fg-muted">
        Events as the streaming pipeline appends them. Each one is checked in your browser against a
        checkpoint signed by the pinned key.
      </p>
      <div className="mt-8">
        <RecentEvents base={base} />
      </div>
    </>
  );
}
