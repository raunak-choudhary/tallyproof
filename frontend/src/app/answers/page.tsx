import type { Metadata } from "next";
import { Suspense } from "react";

import { SavedAnswer } from "@/features/answers/SavedAnswer";

export const metadata: Metadata = { title: "Answer · Tallyproof" };

// One page for every saved answer: the site is a static export, so the answer id travels
// in the query string and the answer is fetched in the browser.
export default function Answers() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-12 md:px-8">
      <p className="text-sm text-fg-muted">A saved answer</p>
      <div className="mt-4">
        <Suspense fallback={<p className="text-fg-muted">Loading…</p>}>
          <SavedAnswer />
        </Suspense>
      </div>
    </main>
  );
}
