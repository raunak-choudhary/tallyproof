"use client";

import { useId, useMemo, useState } from "react";

import type { MatrixCell, MatrixRow } from "@/lib/charts/evalCharts";
import { categoryLabel, OUTCOMES, outcomeInfo } from "@/lib/evals/reports";

// Questions down, runs across, each cell coloured by how the question went. A row that
// stays one colour is a steady result; a row that changes is a flaky one. Every cell is a
// button: choose one to read the question, the answer, and how it was scored.
export function QuestionMatrix({
  rows,
  runIds,
  labels,
  selectedRun,
}: {
  rows: readonly MatrixRow[];
  runIds: readonly string[];
  labels: Record<string, string>;
  selectedRun: string;
}) {
  const id = useId();
  const [picked, setPicked] = useState<{ row: number; col: number } | null>(null);
  const flaky = useMemo(() => rows.filter((r) => !r.steady).length, [rows]);
  const cell: MatrixCell | null = picked ? (rows[picked.row]?.cells[picked.col] ?? null) : null;

  return (
    <figure aria-labelledby={`${id}-t`} className="min-w-0">
      <figcaption id={`${id}-t`} className="text-sm font-medium">
        Every question in every run
        <span className="block text-xs font-normal text-fg-muted">
          {rows.length} questions · {flaky} changed outcome between runs · choose a cell to read it
        </span>
      </figcaption>
      <div
        className="mt-2 overflow-x-auto"
        tabIndex={0}
        aria-label="Question matrix, scrolls sideways"
      >
        <table className="border-separate border-spacing-[3px] text-xs">
          <thead>
            <tr>
              <th scope="col" className="sr-only">
                Question
              </th>
              {runIds.map((r, c) => (
                <th
                  key={r}
                  scope="col"
                  className={`h-5 w-6 min-w-6 p-0 text-center font-mono font-normal ${
                    r === selectedRun ? "text-accent" : "text-fg-muted"
                  }`}
                  title={labels[r]}
                >
                  {c + 1}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={`${row.id}-${i}`}>
                <th
                  scope="row"
                  className="pr-2 text-left font-mono font-normal whitespace-nowrap text-fg-muted"
                  title={row.question}
                >
                  {row.id}
                  {!row.steady && (
                    <span className="ml-1 text-warn" aria-label="changed between runs">
                      ~
                    </span>
                  )}
                </th>
                {row.cells.map((c, col) => {
                  const isPicked = picked?.row === i && picked.col === col;
                  return (
                    <td key={col} className="p-0">
                      {c ? (
                        <button
                          type="button"
                          aria-label={`${row.id}, run ${col + 1}: ${outcomeInfo(c.outcome).label}`}
                          aria-pressed={isPicked}
                          onClick={() => setPicked(isPicked ? null : { row: i, col })}
                          className="block size-6 rounded-[4px] outline-offset-1 aria-pressed:outline-2 aria-pressed:outline-[var(--fg)]"
                          style={{
                            background: outcomeInfo(c.outcome).colour,
                            opacity: runIds[col] === selectedRun || isPicked ? 1 : 0.72,
                          }}
                        />
                      ) : (
                        <span className="block size-6 rounded-[4px] bg-bg-sunken" />
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul
        className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-muted"
        aria-label="Outcomes"
      >
        {OUTCOMES.map((o) => (
          <li key={o.key} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="inline-block size-2.5 rounded-sm"
              style={{ background: o.colour }}
            />
            {o.label}
          </li>
        ))}
      </ul>
      {cell && picked && (
        <div
          className="mt-4 grid gap-2 rounded-[var(--radius)] border border-border bg-bg-elevated p-4 text-sm"
          aria-live="polite"
        >
          <p className="text-xs text-fg-muted">
            {cell.result.id} · {categoryLabel(cell.result.category)} · run {picked.col + 1},{" "}
            {labels[runIds[picked.col]!]}
          </p>
          <p className="font-medium">{cell.result.question}</p>
          <p className="breakable text-fg-muted">
            {cell.result.answer ||
              (cell.result.refusal
                ? `Refused: ${cell.result.refusal.replace(/_/g, " ")}`
                : "No answer")}
          </p>
          <p className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs">
            <span style={{ color: outcomeInfo(cell.outcome).colour }}>
              {outcomeInfo(cell.outcome).label}
            </span>
            {cell.result.numeric_exact !== null && (
              <span>number {cell.result.numeric_exact ? "exact" : "wrong"}</span>
            )}
            {cell.result.must > 0 && (
              <span>
                cited {cell.result.cited_correct} of {cell.result.must} required records
              </span>
            )}
            <span>proofs {cell.result.integrity_ok ? "verified" : "failed"}</span>
          </p>
        </div>
      )}
    </figure>
  );
}
