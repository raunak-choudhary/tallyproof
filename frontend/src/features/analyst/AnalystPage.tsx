"use client";

import { type FormEvent, useState } from "react";

import type { Answer } from "@/lib/analyst/api";
import { answerPath, askQuestion } from "@/lib/analyst/api";
import { apiBase } from "@/lib/live/api";

import { AnswerView } from "./AnswerView";

const EXAMPLES = [
  "How much did the Department of State obligate in fiscal year 2024?",
  "Which payments have no recorded award behind them?",
  "What does the FAR say about interest on advance payments?",
  "How much will NASA spend next year?",
];

export function AnalystPage() {
  const base = apiBase();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!base) {
    return (
      <p className="rounded-[var(--radius)] border border-border bg-bg-elevated p-4">
        The analyst needs the live API, which this static demo doesn&apos;t have. Run the project
        locally with <code className="font-mono">make demo</code> and open this page there.
      </p>
    );
  }

  const ask = async (event?: FormEvent) => {
    event?.preventDefault();
    const text = question.trim();
    if (text.length < 3 || busy) return;
    setBusy(true);
    setError("");
    try {
      setAnswer(await askQuestion(base, text));
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-8">
      <form onSubmit={(e) => void ask(e)} className="space-y-3">
        <label htmlFor="question" className="block font-medium">
          Ask about federal contract spending
        </label>
        <textarea
          id="question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={500}
          rows={3}
          className="w-full rounded-[var(--radius)] border border-border bg-bg-elevated p-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        />
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={busy || question.trim().length < 3}
            className="rounded-[var(--radius)] bg-accent px-4 py-2 font-medium text-bg disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            {busy ? "Asking…" : "Ask"}
          </button>
          <span className="text-sm text-fg-muted">Answers cite records you can verify here.</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => setQuestion(example)}
              className="rounded-full border border-border px-3 py-1 text-left text-sm text-fg-muted hover:border-accent hover:text-fg"
            >
              {example}
            </button>
          ))}
        </div>
      </form>

      {error && (
        <p role="alert" className="text-fail">
          The analyst couldn&apos;t be reached: {error}
        </p>
      )}
      {/* Keyed by answer, so no check or expanded list carries over to the next answer. */}
      {answer && (
        <p className="text-sm text-fg-muted">
          <a
            href={answerPath(answer.answerId)}
            className="text-accent underline-offset-4 hover:underline"
          >
            Link to this answer
          </a>{" "}
          to share it; whoever opens it can verify every citation themselves.
        </p>
      )}
      {answer && <AnswerView key={answer.answerId} base={base} answer={answer} />}
    </div>
  );
}
