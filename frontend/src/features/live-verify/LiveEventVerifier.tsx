"use client";

import { useEffect, useMemo, useState } from "react";

import { VerificationSteps } from "@/features/event-verify/VerificationSteps";
import { MerkleRadial } from "@/features/proof/MerkleRadial";
import type { Climb } from "@/lib/charts/merkleClimb";
import { climb } from "@/lib/charts/merkleClimb";
import type { LiveEvent, LiveProof } from "@/lib/live/api";
import { fetchEvent, fetchProof } from "@/lib/live/api";
import { pinnedVerifierKey } from "@/lib/replay/pinnedKey";
import { canonicalize } from "@/lib/verify/canonical";
import type { VerifyResult } from "@/lib/verify/verifyEvent";
import { verifyEvent } from "@/lib/verify/verifyEvent";
import { utf8 } from "@/lib/verify/bytes";
import { leafHash } from "@/lib/verify/hashing";

function withAmount(canonical: string, amount: string): string {
  const record = JSON.parse(canonical) as { payload: Record<string, unknown> };
  return canonicalize({ ...record, payload: { ...record.payload, amount } });
}

export function LiveEventVerifier({ base, eventId }: { base: string; eventId: string }) {
  const [loaded, setLoaded] = useState<{ event: LiveEvent; proof: LiveProof } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [tampered, setTampered] = useState(false);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [path, setPath] = useState<Climb | null>(null);

  useEffect(() => {
    Promise.all([fetchEvent(base, eventId), fetchProof(base, eventId)])
      .then(([event, proof]) => setLoaded({ event, proof }))
      .catch((error: unknown) =>
        setLoadError(error instanceof Error ? error.message : String(error)),
      );
  }, [base, eventId]);

  const parsed = useMemo(
    () => (loaded ? (JSON.parse(loaded.event.canonical) as Record<string, unknown>) : null),
    [loaded],
  );

  if (loadError) {
    return (
      <p role="alert" className="text-fail">
        Could not load this event from the live API: {loadError}
      </p>
    );
  }
  if (!loaded || !parsed) return <p className="text-fg-muted">Loading from the live API…</p>;

  const { event, proof } = loaded;
  const originalAmount = (parsed.payload as { amount?: string } | undefined)?.amount ?? "";

  const run = (edit: boolean) => {
    const canonical = edit
      ? withAmount(event.canonical, amount || originalAmount)
      : event.canonical;
    setTampered(edit);
    setPath(climb(leafHash(utf8(canonical)), proof.leafIndex, proof.treeSize, proof.auditPath));
    setResult(
      verifyEvent({
        canonical,
        leafIndex: proof.leafIndex,
        publishedLeaves: [],
        auditPath: proof.auditPath,
        checkpointNote: proof.checkpointNote,
        pinnedKey: pinnedVerifierKey(),
      }),
    );
  };

  return (
    <div className="space-y-8">
      <section aria-labelledby="record-heading">
        <h2 id="record-heading" className="text-lg font-semibold">
          The record
        </h2>
        <p className="mt-1 text-sm text-fg-muted">
          Leaf {event.leafIndex}, proved against a signed checkpoint of {proof.treeSize} records
        </p>
        <pre
          tabIndex={0}
          aria-label="The record's canonical bytes, scrollable"
          className="mt-3 overflow-x-auto rounded-[var(--radius)] border border-border bg-bg-elevated p-4 font-mono text-sm"
        >
          {JSON.stringify(parsed, null, 2)}
        </pre>
      </section>

      <section aria-labelledby="verify-heading" className="space-y-4">
        <h2 id="verify-heading" className="text-lg font-semibold">
          Check it yourself
        </h2>
        <div className="flex flex-wrap items-end gap-3">
          <button
            type="button"
            onClick={() => run(false)}
            className="rounded-[var(--radius)] bg-accent px-4 py-2 font-medium text-bg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            Verify this record
          </button>
          <label className="flex flex-col text-sm">
            <span className="text-fg-muted">Try a different amount</span>
            <input
              value={amount}
              placeholder={originalAmount}
              onChange={(e) => setAmount(e.target.value)}
              className="mt-1 w-40 rounded-[var(--radius)] border border-border bg-bg-elevated px-3 py-2 font-mono"
            />
          </label>
          <button
            type="button"
            onClick={() => run(true)}
            className="rounded-[var(--radius)] border border-border px-4 py-2 focus-visible:outline-2 focus-visible:outline-accent"
          >
            Edit the record and verify
          </button>
        </div>
        {result && <VerificationSteps result={result} tampered={tampered} />}
        {result && path && (
          <div className="mt-6">
            <MerkleRadial climbResult={path} signedRoot={result.checkpoint?.rootHash ?? null} />
          </div>
        )}
      </section>
    </div>
  );
}
