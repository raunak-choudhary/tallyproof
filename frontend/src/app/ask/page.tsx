import type { Metadata } from "next";

import { AnalystPage } from "@/features/analyst/AnalystPage";

export const metadata: Metadata = { title: "Ask the analyst · Tallyproof" };

export default function Ask() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-12 md:px-8">
      <h1 className="text-2xl font-semibold">Ask the analyst</h1>
      <p className="mt-2 text-fg-muted">
        Numbers come from queries over the ledger, never from the model, and every claim cites
        records you can check against the signed log.
      </p>
      <div className="mt-8">
        <AnalystPage />
      </div>
    </main>
  );
}
