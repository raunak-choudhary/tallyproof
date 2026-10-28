import type { VerifyResult } from "@/lib/verify/verifyEvent";

// The outcome of a verification and each check behind it, shared by the static and live pages.
export function VerificationSteps({
  result,
  tampered,
}: {
  result: VerifyResult;
  /** True when the reader edited the record, so a failure is the expected outcome. */
  tampered: boolean;
}) {
  return (
    <div aria-live="polite">
      <p className={`font-semibold ${result.ok ? "text-ok" : "text-fail"}`}>
        {result.ok
          ? "Verified: this record is exactly what the signed log committed to."
          : tampered
            ? "Tampering detected. This is the check that caught it:"
            : "Verification failed."}
      </p>
      <ol className="mt-3 space-y-2">
        {result.steps.map((step) => (
          <li key={step.id} className="flex gap-3">
            <span aria-hidden="true" className={step.ok ? "text-ok" : "text-fail"}>
              {step.ok ? "✓" : "✕"}
            </span>
            <span>
              <span className="font-medium">{step.label}</span>
              <span className="sr-only">{step.ok ? " passed" : " failed"}</span>
              <span className="block break-all font-mono text-sm text-fg-muted">{step.detail}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
