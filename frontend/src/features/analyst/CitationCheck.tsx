"use client";

import { useState } from "react";

import { VerificationSteps } from "@/features/event-verify/VerificationSteps";
import { fetchEvent, fetchProof } from "@/lib/live/api";
import { pinnedVerifierKey } from "@/lib/replay/pinnedKey";
import type { VerifyResult } from "@/lib/verify/verifyEvent";
import { verifyEvent } from "@/lib/verify/verifyEvent";

// One cited record and a button that checks it in this browser: the record's
// bytes, its proof at the answer's checkpoint, that checkpoint's signature, and
// that the record, leaf, and checkpoint are the ones the answer cited. With a
// quote, the quoted text must appear in the record itself.
export function CitationCheck({
  base,
  eventId,
  leafIndex,
  treeSize,
  quote,
}: {
  base: string;
  eventId: string;
  leafIndex: number;
  treeSize: number;
  quote?: string;
}) {
  const [state, setState] = useState<"idle" | "checking" | "done" | "error">("idle");
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);

  const check = async () => {
    setState("checking");
    try {
      const [event, proof] = await Promise.all([
        fetchEvent(base, eventId),
        fetchProof(base, eventId, fetch, treeSize),
      ]);
      setResult(
        verifyEvent({
          canonical: event.canonical,
          leafIndex: proof.leafIndex,
          publishedLeaves: [],
          auditPath: proof.auditPath,
          checkpointNote: proof.checkpointNote,
          pinnedKey: pinnedVerifierKey(),
          expected: { eventId, leafIndex, treeSize, ...(quote === undefined ? {} : { quote }) },
        }),
      );
      setState("done");
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setState("error");
    }
  };

  return (
    <li className="py-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <code className="break-all font-mono text-sm">{eventId}</code>
        <span className="text-sm text-fg-muted">leaf {leafIndex}</span>
        {state === "idle" && (
          <button
            type="button"
            onClick={() => void check()}
            className="rounded-[var(--radius)] border border-border px-3 py-1 text-sm hover:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            Verify
          </button>
        )}
        {state === "checking" && <span className="text-sm text-fg-muted">Checking…</span>}
        {state === "error" && (
          <span role="alert" className="text-sm text-fail">
            Couldn&apos;t load the proof: {error}
          </span>
        )}
        {state === "done" && result && (
          <button
            type="button"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            className={`text-sm font-medium underline-offset-4 hover:underline ${result.ok ? "text-ok" : "text-fail"}`}
          >
            {result.ok ? "✓ Verified" : "✕ Failed"} {open ? "(hide steps)" : "(show steps)"}
          </button>
        )}
      </div>
      {open && result && (
        <div className="mt-3 rounded-[var(--radius)] border border-border bg-bg-elevated p-4">
          <VerificationSteps result={result} tampered={false} />
        </div>
      )}
    </li>
  );
}
