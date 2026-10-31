"use client";

import { useEffect, useMemo, useState } from "react";

import type { RecordSource } from "@/lib/analyst/records";
import { bundleRecords } from "@/lib/analyst/records";
import type { Bundle } from "@/lib/replay/bundle";
import { loadBundle } from "@/lib/replay/bundle";
import type { DemoAnswers as Demo } from "@/lib/replay/answers";
import { loadDemoAnswers } from "@/lib/replay/answers";
import { replayBase } from "@/lib/replay/paths";
import { pinnedVerifierKey } from "@/lib/replay/pinnedKey";

import { AnswerView } from "./AnswerView";

// The analyst page on the static site, which has no backend. It shows real answers to a
// fixed list of questions, computed ahead of time on a ledger built from exactly this
// site's replay bundle, so every citation is checked here against the bundle's signed
// checkpoint, the same way a live answer is checked against the API's.
export function DemoAnswers() {
  const [demo, setDemo] = useState<Demo | null>(null);
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [chosen, setChosen] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    const base = replayBase();
    Promise.all([loadDemoAnswers(base), loadBundle(base, pinnedVerifierKey())])
      .then(([answers, loaded]) => {
        setDemo(answers);
        setBundle(loaded);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const records: RecordSource | null = useMemo(
    () => (bundle ? bundleRecords(bundle) : null),
    [bundle],
  );

  if (error) {
    return (
      <p role="alert" className="text-fail">
        The demo answers couldn&apos;t be loaded: {error}
      </p>
    );
  }
  if (!demo || !records) return <p className="text-fg-muted">Loading the demo answers…</p>;
  const answer = demo.answers[chosen];

  return (
    <div className="space-y-8">
      <div className="space-y-3 rounded-[var(--radius)] border border-border bg-bg-elevated p-4">
        <p>
          This static demo can&apos;t take new questions; that needs the live API (run{" "}
          <code className="font-mono">make demo</code>). These are real answers to{" "}
          {demo.answers.length} fixed questions, computed by the same analyst ({demo.answerModel})
          over the {demo.treeSize.toLocaleString("en-US")} records in this site&apos;s replay data.
          Every record they cite is checked here against the signed checkpoint.
        </p>
      </div>
      <div role="group" aria-label="Demo questions" className="flex flex-wrap gap-2">
        {demo.answers.map((a, i) => (
          <button
            key={a.answerId}
            type="button"
            onClick={() => setChosen(i)}
            aria-pressed={i === chosen}
            className={`rounded-full border px-3 py-1 text-left text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
              i === chosen
                ? "border-accent text-fg"
                : "border-border text-fg-muted hover:border-accent hover:text-fg"
            }`}
          >
            {a.question}
          </button>
        ))}
      </div>
      {answer && (
        <div className="space-y-4">
          <h2 className="text-xl font-semibold">{answer.question}</h2>
          {/* Keyed by answer, so no check or expanded list carries over to the next one. */}
          <AnswerView key={answer.answerId} records={records} totalsBase={null} answer={answer} />
        </div>
      )}
    </div>
  );
}
