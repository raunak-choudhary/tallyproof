"use client";

import { useEffect, useMemo, useState } from "react";

import type { Bundle } from "@/lib/replay/bundle";
import { loadBundle } from "@/lib/replay/bundle";
import { replayBase } from "@/lib/replay/paths";
import { pinnedVerifierKey } from "@/lib/replay/pinnedKey";
import { utf8 } from "@/lib/verify/bytes";
import { canonicalize } from "@/lib/verify/canonical";
import { leafHash } from "@/lib/verify/hashing";
import type { VerifyResult } from "@/lib/verify/verifyEvent";
import { forgeCheckpointWithNewRoot, verifyEvent } from "@/lib/verify/verifyEvent";

import { VerificationSteps } from "./VerificationSteps";

type Mode = "original" | "edited" | "rebuilt";

function withAmount(canonical: string, amount: string): string {
  const record = JSON.parse(canonical) as { payload: Record<string, unknown> };
  return canonicalize({ ...record, payload: { ...record.payload, amount } });
}

export function EventVerifier({ eventId }: { eventId: string }) {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [amount, setAmount] = useState<string>("");
  const [mode, setMode] = useState<Mode>("original");
  const [result, setResult] = useState<VerifyResult | null>(null);

  useEffect(() => {
    loadBundle(replayBase(), pinnedVerifierKey())
      .then(setBundle)
      .catch((error: unknown) =>
        setLoadError(error instanceof Error ? error.message : String(error)),
      );
  }, []);

  const record = useMemo(
    () => bundle?.records.find((r) => r.eventId === eventId),
    [bundle, eventId],
  );
  const parsed = useMemo(
    () => (record ? (JSON.parse(record.canonical) as Record<string, unknown>) : null),
    [record],
  );
  const originalAmount = (parsed?.payload as { amount?: string } | undefined)?.amount ?? "";

  if (loadError) {
    return (
      <p role="alert" className="text-fail">
        The bundle failed its integrity check: {loadError}
      </p>
    );
  }
  if (!bundle || !record || !parsed)
    return <p className="text-fg-muted">Loading the signed bundle…</p>;

  const run = (nextMode: Mode) => {
    const editedAmount = amount || originalAmount;
    const canonical =
      nextMode === "original" ? record.canonical : withAmount(record.canonical, editedAmount);
    const note =
      nextMode === "rebuilt"
        ? forgeCheckpointWithNewRoot(
            bundle.latestCheckpointNote,
            bundle.leaves,
            record.leafIndex,
            canonical,
          )
        : bundle.latestCheckpointNote;
    const leaves =
      nextMode === "rebuilt"
        ? // The attacker publishes a rebuilt log containing the edited record's real leaf.
          bundle.leaves.map((leaf, i) =>
            i === record.leafIndex ? leafHash(utf8(canonical)) : leaf,
          )
        : bundle.leaves;
    setMode(nextMode);
    setResult(
      verifyEvent({
        canonical,
        leafIndex: record.leafIndex,
        publishedLeaves: leaves,
        checkpointNote: note,
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
          Leaf {record.leafIndex} of {bundle.manifest.tree_size} in log {bundle.manifest.origin}
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
            onClick={() => run("original")}
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
            onClick={() => run("edited")}
            className="rounded-[var(--radius)] border border-border px-4 py-2 focus-visible:outline-2 focus-visible:outline-accent"
          >
            Edit the record and verify
          </button>
          <button
            type="button"
            onClick={() => run("rebuilt")}
            className="rounded-[var(--radius)] border border-border px-4 py-2 focus-visible:outline-2 focus-visible:outline-accent"
          >
            Also rebuild the tree (no key)
          </button>
        </div>

        {result && <VerificationSteps result={result} tampered={mode !== "original"} />}
      </section>
    </div>
  );
}
