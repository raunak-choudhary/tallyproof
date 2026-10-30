import type { Metadata } from "next";

import { EvalsPage } from "@/features/evals/EvalsPage";

export const metadata: Metadata = { title: "Evaluation · Tallyproof" };

export default function Evals() {
  return (
    <main className="mx-auto grid max-w-[1200px] gap-8 px-[var(--gutter)] py-12">
      <header className="grid max-w-3xl gap-3">
        <p className="text-xs font-semibold tracking-[0.14em] text-accent-2 uppercase">
          Evaluation
        </p>
        <h1 className="display text-[length:var(--text-2xl)] font-normal">
          How well does the analyst answer?
        </h1>
        <p className="text-fg-muted">
          Every answer is scored against an oracle that never sees the analyst&apos;s code. Each run
          is a published report, so every number here can be traced to the questions and answers
          behind it.
        </p>
      </header>
      <EvalsPage />
    </main>
  );
}
