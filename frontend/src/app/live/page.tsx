import { Suspense } from "react";

import { LivePage } from "@/features/live-verify/LivePage";

// A single static page: the event ID comes from the query string and the data
// from the live API, so nothing about live events needs to exist at build time.
export default function Live() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-12 md:px-8">
      <p className="text-sm text-fg-muted">Live ledger event</p>
      <Suspense fallback={<p className="text-fg-muted">Loading…</p>}>
        <LivePage />
      </Suspense>
    </main>
  );
}
