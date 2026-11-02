"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { VerificationSteps } from "@/features/event-verify/VerificationSteps";
import { MerkleRadial } from "@/features/proof/MerkleRadial";
import type { Climb } from "@/lib/charts/merkleClimb";
import { climb, shortHex } from "@/lib/charts/merkleClimb";
import type { Bundle } from "@/lib/replay/bundle";
import { loadBundle } from "@/lib/replay/bundle";
import { replayBase } from "@/lib/replay/paths";
import { pinnedVerifierKey } from "@/lib/replay/pinnedKey";
import type { Level, WitnessCheck } from "@/lib/tamper/attacks";
import { ATTACKS, stage, witnessCheck, witnessedBefore } from "@/lib/tamper/attacks";
import { equal, utf8 } from "@/lib/verify/bytes";
import { parseCheckpoint } from "@/lib/verify/checkpoint";
import { leafHash } from "@/lib/verify/hashing";
import { inclusionProof } from "@/lib/verify/merkle";
import type { VerifyResult } from "@/lib/verify/verifyEvent";
import { verifyEvent } from "@/lib/verify/verifyEvent";

interface Outcome {
  level: Level;
  result: VerifyResult;
  path: Climb;
  witness: WitnessCheck | null;
  signedRoot: Uint8Array | null;
  /** Level 4: whether the climb reaches the root the attacker wrote into the checkpoint. */
  attackerRootMatches: boolean;
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

// Four attacks on one real record, each run here against the signed bundle. The browser
// catches the first three with the checks it runs on every record; the fourth, a stolen
// key, is caught by the outside witness through a consistency proof.
export function TamperPage() {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  useEffect(() => {
    loadBundle(replayBase(), pinnedVerifierKey())
      .then(setBundle)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  // A record before the witnessed checkpoint, so level 4 has something to catch.
  const target = useMemo(() => {
    if (!bundle) return null;
    const witnessed = witnessedBefore(
      bundle.checkpoints,
      bundle.leaves.length,
      pinnedVerifierKey(),
    );
    const limit = witnessed ? witnessed.treeSize : bundle.records.length;
    const record =
      bundle.records.find(
        (r) => r.leafIndex < limit && r.canonical.includes('"obligation.recorded"'),
      ) ?? bundle.records[0];
    if (!record) return null;
    const parsed = JSON.parse(record.canonical) as {
      payload: { amount: string; awarding_agency?: string; piid?: string };
    };
    return {
      record,
      amount: parsed.payload.amount,
      agency: parsed.payload.awarding_agency,
      piid: parsed.payload.piid,
      witnessed,
    };
  }, [bundle]);

  if (error)
    return (
      <p role="alert" className="text-fail">
        The bundle failed its integrity check: {error}
      </p>
    );
  if (!bundle || !target) return <p className="text-fg-muted">Loading the signed bundle…</p>;

  const edited = (Number(target.amount) + 0.01).toFixed(2);
  const run = (level: Level) => {
    const key = pinnedVerifierKey();
    const staged = stage(
      level,
      target.record.canonical,
      target.record.leafIndex,
      bundle.leaves,
      bundle.latestCheckpointNote,
      edited,
    );
    const result = verifyEvent({
      canonical: staged.canonical,
      leafIndex: target.record.leafIndex,
      publishedLeaves: staged.leaves,
      checkpointNote: staged.note,
      pinnedKey: key,
    });
    const path = climb(
      leafHash(utf8(staged.canonical)),
      target.record.leafIndex,
      staged.leaves.length,
      inclusionProof(staged.leaves, target.record.leafIndex),
    );
    let signedRoot: Uint8Array | null = result.checkpoint?.rootHash ?? null;
    let witness: WitnessCheck | null = null;
    if (staged.assumeSigned) {
      // The signature is taken as valid, standing in for a stolen key.
      try {
        signedRoot = parseCheckpoint(staged.note.split("\n\n")[0] + "\n").rootHash;
      } catch {
        signedRoot = null;
      }
      witness = target.witnessed ? witnessCheck(target.witnessed, staged.leaves) : null;
    }
    setOutcome({
      level,
      result,
      path,
      witness,
      signedRoot,
      attackerRootMatches: signedRoot !== null && equal(path.computedRoot, signedRoot),
    });
  };

  return (
    <main className="mx-auto grid max-w-[1200px] gap-8 px-[var(--gutter)] py-10">
      <header className="grid gap-3">
        <p className="text-xs font-semibold tracking-[0.14em] text-accent-2 uppercase">
          The tamper ladder
        </p>
        <h1 className="display text-[length:var(--text-2xl)] font-normal">
          Try to tamper with it.
        </h1>
        <p className="max-w-[68ch] text-fg-muted">
          Four attacks, from editing one record to rewriting history with the real key. Your browser
          carries out each one on the signed bundle and runs the same checks it runs on every
          record. Nothing is sent anywhere.
        </p>
      </header>

      <section className="rounded-[var(--radius-lg)] border border-border bg-bg-elevated p-4">
        <h2 className="text-sm font-medium">The record under attack</h2>
        <p className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-sm">
          <Link
            href={`/ledger/events/${target.record.eventId}/`}
            className="breakable text-accent hover:underline"
          >
            {target.record.eventId}
          </Link>
          <span className="text-fg-muted">
            leaf {target.record.leafIndex} · {target.agency ?? "modification"}
            {target.piid ? ` · ${target.piid}` : ""} · {usd.format(Number(target.amount))}
          </span>
        </p>
        <p className="mt-2 text-xs text-fg-muted">
          Each attack changes the amount to {usd.format(Number(edited))}.
          {target.witnessed
            ? ` An outside witness timestamped the checkpoint at ${target.witnessed.treeSize.toLocaleString("en-US")} records; the record sits before it.`
            : ""}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setOutcome(null)}
            disabled={!outcome}
            aria-disabled={!outcome}
          >
            Reset the record
          </Button>
          <span className="text-xs text-fg-muted">
            {outcome
              ? "The attack only touched a copy in your browser. Resetting restores the signed record, so you can run another attack."
              : "Run an attack below. Reset restores the signed record afterwards, so you can try another."}
          </span>
        </div>
      </section>

      <ol className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {ATTACKS.map((a) => (
          <li
            key={a.level}
            className={`grid content-start gap-3 rounded-[var(--radius-lg)] border p-4 ${outcome?.level === a.level ? "border-accent" : "border-border"}`}
          >
            <span className="text-xs font-semibold tracking-[0.1em] text-fg-muted uppercase">
              Level {a.level}
            </span>
            <h2 className="text-lg font-semibold">{a.title}</h2>
            <p className="text-sm text-fg-muted">{a.does}</p>
            <Button onClick={() => run(a.level)} aria-pressed={outcome?.level === a.level}>
              Run attack
            </Button>
            <p className="text-xs text-fg-muted">
              <span className="font-medium text-fg">Caught by:</span> {a.caught}
            </p>
          </li>
        ))}
      </ol>

      {outcome && (
        <section
          aria-live="polite"
          className="grid gap-6 rounded-[var(--radius-lg)] border border-border bg-bg-elevated p-4 md:grid-cols-[3fr_2fr]"
        >
          <div className="min-w-0">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-sm font-medium">
                Level {outcome.level}: {ATTACKS[outcome.level - 1]?.title}
              </h2>
              <Button variant="ghost" size="sm" onClick={() => setOutcome(null)}>
                Reset
              </Button>
            </div>
            <div className="mt-3">
              {outcome.level === 4 ? (
                <div>
                  <p className="font-semibold text-warn">
                    With the real key, every check on the record passes. So the browser asks the
                    witness.
                  </p>
                  <ol className="mt-3 space-y-2">
                    {[
                      {
                        id: "leaf",
                        ok: true,
                        label: "Leaf hash recomputed in your browser",
                        detail: `${shortHex(outcome.path.hops[0]?.self ?? outcome.path.computedRoot)}…`,
                      },
                      {
                        id: "inclusion",
                        ok: outcome.attackerRootMatches,
                        label: "Leaf reaches the root the attacker signed",
                        detail: `${outcome.path.hops.length} sibling hashes, root ${shortHex(outcome.path.computedRoot)}`,
                      },
                      {
                        id: "signature",
                        ok: true,
                        label: "Checkpoint signed by the pinned key",
                        detail: "assumed: the attacker holds the key",
                      },
                    ].map((s) => (
                      <li key={s.id} className="flex gap-3">
                        <span aria-hidden="true" className={s.ok ? "text-ok" : "text-fail"}>
                          {s.ok ? "✓" : "✕"}
                        </span>
                        <span>
                          <span className="font-medium">{s.label}</span>
                          <span className="block break-all font-mono text-sm text-fg-muted">
                            {s.detail}
                          </span>
                        </span>
                      </li>
                    ))}
                    {outcome.witness && (
                      <li className="flex gap-3">
                        <span
                          aria-hidden="true"
                          className={outcome.witness.ok ? "text-ok" : "text-fail"}
                        >
                          {outcome.witness.ok ? "✓" : "✕"}
                        </span>
                        <span>
                          <span className="font-medium">
                            Consistent with the checkpoint witnessed at{" "}
                            {outcome.witness.firstSize.toLocaleString("en-US")} records
                          </span>
                          <span className="block font-mono text-sm text-fg-muted">
                            {outcome.witness.detail}
                          </span>
                        </span>
                      </li>
                    )}
                  </ol>
                </div>
              ) : (
                <VerificationSteps result={outcome.result} tampered />
              )}
            </div>
          </div>
          <div className="min-w-0">
            <MerkleRadial
              climbResult={outcome.path}
              signedRoot={outcome.signedRoot}
              title={
                outcome.level === 4
                  ? "The rewritten log's audit path"
                  : "The audit path under attack"
              }
            />
          </div>
        </section>
      )}
    </main>
  );
}
