"use client";

import { useState } from "react";

import { docsPath } from "@/lib/release/info";

interface Stage {
  id: string;
  name: string;
  tech: string;
  body: string;
  doc: string;
}

// From a bulk file to a verified answer, one stage at a time. Each stage is a button;
// choosing one opens what it does and where the documentation covers it.
const STAGES: readonly Stage[] = [
  {
    id: "source",
    name: "Public records",
    tech: "USAspending, Treasury",
    body: "Federal contract transactions and outlays come from USAspending's bulk files, and daily cash from the Treasury's API. Nothing is invented: every record on this site is a real one, with personal contact details removed.",
    doc: "data-profile/",
  },
  {
    id: "clean",
    name: "Clean and check",
    tech: "Spark, Deequ",
    body: "Spark reads the bulk files into a lake, cleans them, and runs data-quality checks with Deequ. A file that fails its checks stops the pipeline instead of reaching the ledger.",
    doc: "architecture/#containers",
  },
  {
    id: "stream",
    name: "Stream",
    tech: "Kafka (Redpanda)",
    body: "Clean records become events on a Kafka topic. A record delivered twice carries the same idempotency key, so the ledger keeps one copy: processed effectively once.",
    doc: "architecture/#ingestion-processed-effectively-once",
  },
  {
    id: "ledger",
    name: "Ledger",
    tech: "Postgres, append-only",
    body: "Each event is stored as canonical bytes in an append-only table. The database role the app uses can insert but never update or delete, and everything else (journal, reconciliation) is derived and can be rebuilt.",
    doc: "architecture/#immutability",
  },
  {
    id: "log",
    name: "Merkle log",
    tech: "RFC 9162",
    body: "Every event's bytes are hashed into a leaf of a Merkle tree, the same structure Certificate Transparency uses. One root commits to every record, and a short list of hashes proves any one of them is in it.",
    doc: "architecture/#canonical-bytes",
  },
  {
    id: "checkpoint",
    name: "Signed checkpoint",
    tech: "Ed25519",
    body: "Every few seconds the root is written into a checkpoint note and signed. This site trusts exactly one public key, built into the page, never one served with the data.",
    doc: "architecture/#checkpointing",
  },
  {
    id: "witness",
    name: "Outside witness",
    tech: "Bitcoin timestamps",
    body: "Checkpoints are timestamped in Bitcoin through OpenTimestamps and published on a second origin. A later log must extend what was witnessed, so even the key's holder can't quietly rewrite history.",
    doc: "architecture/#tamper-detection",
  },
  {
    id: "analyst",
    name: "Analyst",
    tech: "Typed queries, bound values",
    body: "A question becomes a typed query the server compiles and runs against the ledger as of one checkpoint. The model writes the sentences, but every number in them is a value from the query, cited to its records.",
    doc: "architecture/#from-question-to-verified-answer",
  },
  {
    id: "browser",
    name: "Your browser",
    tech: "Verify",
    body: "Your browser recomputes each record's hash, walks its proof to the signed root, checks the signature and the witness, and compares what the page shows with the verified bytes. Nothing is taken on the server's word.",
    doc: "adr/0015-verification-trust-model/",
  },
];

export function ArchitectureFlow() {
  const [open, setOpen] = useState(STAGES[0]!.id);
  const stage = STAGES.find((s) => s.id === open)!;
  return (
    <div className="grid gap-4">
      <ol className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-9" aria-label="Stages">
        {STAGES.map((s, i) => (
          <li key={s.id} className="min-w-0">
            <button
              type="button"
              onClick={() => setOpen(s.id)}
              aria-pressed={s.id === open}
              aria-controls="stage-detail"
              className="grid h-full w-full content-start gap-1 rounded-[var(--radius)] border border-border bg-bg-elevated p-3 text-left transition-colors hover:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent aria-pressed:border-accent aria-pressed:bg-bg-sunken"
            >
              <span className="font-mono text-xs text-fg-muted">{i + 1}</span>
              <span className="text-sm font-medium">{s.name}</span>
              <span className="breakable text-xs text-fg-muted">{s.tech}</span>
            </button>
          </li>
        ))}
      </ol>
      <div
        id="stage-detail"
        aria-live="polite"
        className="grid gap-2 rounded-[var(--radius)] border border-border bg-bg-elevated p-4"
      >
        <p className="text-xs font-semibold tracking-[0.12em] text-accent-2 uppercase">
          {STAGES.indexOf(stage) + 1} · {stage.name}
        </p>
        <p className="max-w-[65ch]">{stage.body}</p>
        <a
          href={`${docsPath()}${stage.doc}`}
          className="w-fit text-sm text-accent underline-offset-4 hover:underline"
        >
          Read more in the documentation
        </a>
      </div>
    </div>
  );
}
