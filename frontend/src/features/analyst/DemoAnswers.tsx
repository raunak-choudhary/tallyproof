"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import type { RecordSource } from "@/lib/analyst/records";
import { bundleRecords } from "@/lib/analyst/records";
import type { Bundle } from "@/lib/replay/bundle";
import { loadBundle } from "@/lib/replay/bundle";
import type { DemoAnswers as Demo } from "@/lib/replay/answers";
import { loadDemoAnswers } from "@/lib/replay/answers";
import { docsPath, mediaPath } from "@/lib/release/info";
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
      <section
        aria-labelledby="demo-how"
        className="space-y-4 rounded-[var(--radius)] border border-border bg-bg-elevated p-4"
      >
        <div>
          <h2 id="demo-how" className="font-semibold">
            These {demo.answers.length} answers are real, from the complete system.
          </h2>
          <p className="mt-1 text-sm text-fg-muted">
            Each question was put to the full analyst: it routed the question, filled a typed query,
            ran SQL over a ledger built from exactly the {demo.treeSize.toLocaleString("en-US")}{" "}
            records on this site, and bound every number to the records behind it. The model (
            {demo.answerModel}) chose the query and wrote the words around the numbers; it never
            typed a figure. The answers and their proofs were saved, and your browser checks every
            citation against the signed checkpoint, the same check a live answer gets.
          </p>
        </div>
        <div>
          <h3 className="text-sm font-semibold">Why you can&apos;t type a new question here</h3>
          <p className="mt-1 text-sm text-fg-muted">
            This site is static files with no server behind it. A new question needs the ledger
            database, the query compiler with its SQL guard, and the proof API, and those run on a
            server, not in a page. A model key alone would not be enough, because the numbers never
            come from the model. The live mode is complete; it runs wherever you start the stack,
            and the{" "}
            <Link href="/evals/" className="text-accent underline underline-offset-4">
              evaluation page
            </Link>{" "}
            shows it scored on all 218 questions.
          </p>
        </div>
        <div>
          <h3 className="text-sm font-semibold">To ask your own questions</h3>
          <p className="mt-1 text-sm text-fg-muted">
            Clone the repository, put a Groq key in <code className="font-mono">.env</code>, and run{" "}
            <code className="font-mono">make demo</code> then{" "}
            <code className="font-mono">make web-live</code>. This page then takes any question and
            answers it the same way, with proofs you verify here. See{" "}
            <a
              href={mediaPath("videos/tallyproof-product-demo.mp4")}
              className="text-accent underline underline-offset-4"
            >
              the product demo
            </a>{" "}
            for the analyst answering a question and the browser checking its citations, and{" "}
            <a href={`${docsPath()}runbook/`} className="text-accent underline underline-offset-4">
              the runbook
            </a>{" "}
            for the exact setup.
          </p>
        </div>
      </section>
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
