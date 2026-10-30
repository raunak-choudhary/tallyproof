"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AnswerView } from "@/features/analyst/AnswerView";
import type { Answer } from "@/lib/analyst/api";
import { fetchAnswer } from "@/lib/analyst/api";
import { apiBase } from "@/lib/live/api";

// A saved answer, opened from a shared link. The answer is fetched from the API and every
// citation is verified here, in the reader's browser, exactly as on the analyst page.
export function SavedAnswer() {
  const base = apiBase();
  const answerId = useSearchParams().get("id");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!base || !answerId) return;
    fetchAnswer(base, answerId)
      .then(setAnswer)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [base, answerId]);

  if (!base) {
    return (
      <p className="rounded-[var(--radius)] border border-border bg-bg-elevated p-4">
        Saved answers live in the analyst&apos;s API, which this static demo doesn&apos;t have. Run
        the project locally with <code className="font-mono">make demo</code> and open the link
        there.
      </p>
    );
  }
  if (!answerId) return <p className="text-fg-muted">This link doesn&apos;t name an answer.</p>;
  if (error)
    return (
      <p role="alert" className="text-fail">
        The answer couldn&apos;t be loaded: {error}
      </p>
    );
  if (!answer) return <p className="text-fg-muted">Loading the answer…</p>;
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">{answer.question}</h2>
      <AnswerView base={base} answer={answer} />
    </div>
  );
}
