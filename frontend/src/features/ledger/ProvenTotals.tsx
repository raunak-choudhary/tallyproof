"use client";

import { useEffect, useState } from "react";

import type { BundleTotals } from "@/lib/replay/totals";
import { loadTotals } from "@/lib/replay/totals";
import { pinnedVerifierKey } from "@/lib/replay/pinnedKey";
import { formatCents } from "@/lib/verify/sumTree";
import type { TotalCheckResult } from "@/lib/verify/totalCheck";
import { checkTotal } from "@/lib/verify/totalCheck";

const usd = (cents: bigint) =>
  `$${formatCents(cents).replace(/^(-?)(\d+)/, (_, sign: string, whole: string) => `${sign}${Number(whole).toLocaleString("en-US")}`)}`;

// Each agency's obligations in the replay log, proven in this browser from a signed
// Merkle-sum tree root and a few dozen nodes, without loading the records behind them.
export function ProvenTotals({ base, treeSize }: { base: string; treeSize: number | null }) {
  const [totals, setTotals] = useState<BundleTotals | null>(null);
  const [results, setResults] = useState<TotalCheckResult[] | null>(null);

  useEffect(() => {
    void loadTotals(base).then(setTotals);
  }, [base]);

  if (!totals) return null;
  const rows = totals.totals
    .map((t, i) => ({ ...t, i }))
    .filter((t) => t.entity === "obligations")
    .sort((a, b) =>
      a.agency === null ? -1 : b.agency === null ? 1 : Number(b.totalCents - a.totalCents),
    );

  const verifyAll = () => {
    const key = pinnedVerifierKey();
    setResults(
      totals.totals.map((t) =>
        checkTotal({
          totalsNote: totals.note,
          proof: t.proof,
          pinnedKey: key,
          expected: {
            treeSize: treeSize ?? totals.treeSize,
            amount: formatCents(t.totalCents),
            count: t.count,
          },
        }),
      ),
    );
  };
  const passed = results?.filter((r) => r.ok).length ?? 0;

  return (
    <section
      aria-labelledby="proven-totals"
      className="min-w-0 rounded-[var(--radius-lg)] border border-border bg-bg-elevated p-4"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="proven-totals" className="text-sm font-medium">
          Totals, proven without the records
        </h2>
        <button
          type="button"
          onClick={verifyAll}
          className="rounded-[var(--radius)] border border-border px-3 py-1 text-sm hover:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          Verify every total
        </button>
      </div>
      <p className="mt-1 max-w-[65ch] text-sm text-fg-muted">
        Each total comes with a proof of a few dozen tree nodes, checked here against a signed
        Merkle-sum tree root. A record hidden from a total, or slipped into one, would fail.
      </p>
      {results && (
        <p
          role="status"
          className={`mt-2 text-sm ${passed === results.length ? "text-ok" : "text-fail"}`}
        >
          {passed === results.length
            ? `✓ All ${results.length} totals proven against checkpoint ${totals.treeSize.toLocaleString("en-US")}`
            : `✕ ${results.length - passed} of ${results.length} totals failed`}
        </p>
      )}
      <div
        className="mt-3 overflow-x-auto"
        tabIndex={0}
        aria-label="Proven totals, scrolls sideways"
      >
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-fg-muted">
            <tr>
              <th scope="col" className="py-2 pr-4 font-medium">
                Awarding agency
              </th>
              <th scope="col" className="py-2 pr-4 text-right font-medium">
                Obligated
              </th>
              <th scope="col" className="py-2 pr-4 text-right font-medium">
                Records
              </th>
              <th scope="col" className="py-2 font-medium">
                <span className="sr-only">Proof</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((t) => {
              const result = results?.[t.i];
              return (
                <tr key={t.agency ?? "all"}>
                  <td className="py-2 pr-4">{t.agency ?? <strong>Every agency</strong>}</td>
                  <td className="py-2 pr-4 text-right font-mono tabular-nums">
                    {usd(t.totalCents)}
                  </td>
                  <td className="py-2 pr-4 text-right tabular-nums">
                    {t.count.toLocaleString("en-US")}
                  </td>
                  <td className="py-2">
                    {result && (
                      <span className={result.ok ? "text-ok" : "text-fail"}>
                        {result.ok ? "✓ proven" : "✕ failed"}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-fg-muted">
        The agency rows don&apos;t add up to every agency: records whose award was first recorded
        outside this slice of the log have no agency here.
      </p>
    </section>
  );
}
