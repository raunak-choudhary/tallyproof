"use client";

import { useState } from "react";

import { fetchTotalProof } from "@/lib/live/api";
import { pinnedVerifierKey } from "@/lib/replay/pinnedKey";
import { formatCents } from "@/lib/verify/sumTree";
import type { TotalCheckResult } from "@/lib/verify/totalCheck";
import { checkTotal } from "@/lib/verify/totalCheck";

// Proves a whole total in this browser from a few dozen tree nodes: the signed sum
// tree's note, its checkpoint, the proof, and that the answer shows what it proves.
export function TotalCheck({
  base,
  path,
  treeSize,
  amount,
  count,
}: {
  base: string;
  path: string;
  treeSize: number;
  amount?: string;
  count?: number;
}) {
  const [state, setState] = useState<"idle" | "checking" | "done" | "error">("idle");
  const [result, setResult] = useState<TotalCheckResult | null>(null);
  const [error, setError] = useState("");

  const check = async () => {
    setState("checking");
    try {
      const body = await fetchTotalProof(base, path);
      setResult(
        checkTotal({
          totalsNote: body.totalsNote,
          proof: body.proof,
          pinnedKey: pinnedVerifierKey(),
          expected: {
            treeSize,
            ...(amount === undefined ? {} : { amount }),
            ...(count === undefined ? {} : { count }),
          },
        }),
      );
      setState("done");
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setState("error");
    }
  };

  return (
    <div className="mt-3 rounded-[var(--radius)] border border-border bg-bg-elevated p-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-sm font-medium">The whole total</span>
        {state === "idle" && (
          <button
            type="button"
            onClick={() => void check()}
            className="rounded-[var(--radius)] border border-border px-3 py-1 text-sm hover:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            Verify the total
          </button>
        )}
        {state === "checking" && <span className="text-sm text-fg-muted">Checking…</span>}
        {state === "error" && (
          <span role="alert" className="text-sm text-fail">
            Couldn&apos;t load the proof: {error}
          </span>
        )}
        {state === "done" && result && (
          <span
            role="status"
            className={`text-sm font-medium ${result.ok ? "text-ok" : "text-fail"}`}
          >
            {result.ok && result.proven
              ? `✓ Proven: ${result.proven.count.toLocaleString("en-US")} records, ${formatCents(result.proven.total)}`
              : "✕ Failed"}
          </span>
        )}
      </div>
      {state === "done" && result && (
        <ol className="mt-2 space-y-1 text-sm">
          {result.steps.map((step) => (
            <li key={step.id} className="flex gap-2">
              <span aria-hidden="true" className={step.ok ? "text-ok" : "text-fail"}>
                {step.ok ? "✓" : "✕"}
              </span>
              <span>
                <span className="font-medium">{step.label}.</span>{" "}
                <span className="text-fg-muted">{step.detail}</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
