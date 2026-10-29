"use client";

import { useState } from "react";

import type { Answer, Citation } from "@/lib/analyst/api";
import { assuranceNote, sampleNote, segments } from "@/lib/analyst/api";

import { CitationCheck } from "./CitationCheck";

const SHOWN = 10;

function CitationBlock({
  base,
  citation,
  treeSize,
}: {
  base: string;
  citation: Citation;
  treeSize: number;
}) {
  const [all, setAll] = useState(false);
  const events = all ? citation.events : citation.events.slice(0, SHOWN);
  return (
    <li
      id={`cite-${citation.label}`}
      className="scroll-mt-24 rounded-[var(--radius)] border border-border p-4"
    >
      <p className="font-medium">
        <span className="font-mono text-accent">[{citation.label}]</span> {citation.meaning}
        <span className="text-fg-muted">
          {" "}
          · {(citation.sampleOf ?? citation.events.length).toLocaleString("en-US")} records
        </span>
      </p>
      {sampleNote(citation, treeSize) && (
        <p className="mt-1 text-sm text-warn">{sampleNote(citation, treeSize)}</p>
      )}
      <ul className="mt-2 divide-y divide-border">
        {events.map((e) => (
          <CitationCheck
            key={`${e.eventId}@${treeSize}`}
            base={base}
            eventId={e.eventId}
            leafIndex={e.leafIndex}
            treeSize={treeSize}
          />
        ))}
      </ul>
      {citation.events.length > SHOWN && (
        <button
          type="button"
          onClick={() => setAll(!all)}
          className="mt-2 text-sm text-accent underline-offset-4 hover:underline"
        >
          {all ? "Show fewer" : `Show all ${citation.events.length}`}
        </button>
      )}
    </li>
  );
}

// An answer as the analyst returned it. Every value links to its citation, and
// every citation's records can be verified here, against the answer's checkpoint.
export function AnswerView({ base, answer }: { base: string; answer: Answer }) {
  if (answer.status === "refused") {
    return (
      <section aria-live="polite" className="rounded-[var(--radius)] border border-warn p-4">
        <h2 className="font-semibold text-warn">Not answered</h2>
        <p className="mt-1">{answer.refusal?.message || "The analyst declined this question."}</p>
        <p className="mt-2 text-sm text-fg-muted">Reason code: {answer.refusal?.code}</p>
      </section>
    );
  }
  return (
    <section aria-live="polite" className="space-y-6">
      <div>
        <h2 className="sr-only">Answer</h2>
        <p className="text-lg leading-relaxed">
          {segments(answer.text).map((part, i) =>
            part.kind === "text" ? (
              <span key={i}>{part.text}</span>
            ) : (
              <a
                key={i}
                href={`#cite-${part.label}`}
                className="mx-0.5 font-mono text-sm text-accent underline-offset-4 hover:underline"
              >
                [{part.label}]
              </a>
            ),
          )}
        </p>
        <p className="mt-3 text-sm text-fg-muted">{assuranceNote(answer.assurance)}</p>
        {answer.filterWords && (
          <p className="mt-1 text-sm text-fg-muted">
            Records used: <span className="text-fg">{answer.filterWords}</span>, as of checkpoint{" "}
            {answer.treeSize.toLocaleString("en-US")}.
          </p>
        )}
      </div>

      {answer.quotes.length > 0 && (
        <div className="space-y-3">
          <h3 className="font-semibold">Quoted regulation</h3>
          {answer.quotes.map((q) => (
            <figure
              key={q.source}
              id={`cite-${q.source}`}
              className="scroll-mt-24 rounded-[var(--radius)] border border-border p-4"
            >
              <blockquote className="border-l-2 border-accent pl-3">{q.text}</blockquote>
              <figcaption className="mt-2 text-sm text-fg-muted">
                FAR {q.section}, {q.title}
              </figcaption>
              <ul className="mt-1">
                <CitationCheck
                  key={`${q.eventId}@${answer.treeSize}`}
                  base={base}
                  eventId={q.eventId}
                  leafIndex={q.leafIndex}
                  treeSize={answer.treeSize}
                  quote={q.text}
                />
              </ul>
            </figure>
          ))}
        </div>
      )}

      {answer.slots.length > 0 && (
        <div>
          <h3 className="font-semibold">Values</h3>
          <dl className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 text-sm md:grid-cols-[auto_1fr]">
            {answer.slots.map((s) => (
              <div key={s.label} className="contents">
                <dt className="font-mono">{s.display}</dt>
                <dd className="text-fg-muted">
                  {s.meaning}
                  {s.citation && <span className="font-mono text-accent"> [{s.citation}]</span>}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {answer.citations.length > 0 && (
        <div>
          <h3 className="font-semibold">Citations</h3>
          <ul className="mt-2 space-y-3">
            {answer.citations.map((c) => (
              <CitationBlock key={c.label} base={base} citation={c} treeSize={answer.treeSize} />
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
