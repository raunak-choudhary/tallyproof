import { buildInfo, docsPath } from "@/lib/release/info";
import { pinnedVerifierKey } from "@/lib/replay/pinnedKey";

// Names the commit the site was built from, so anyone can check the code that verified
// their proof; shows the fingerprint of the only key this site trusts; and links the
// documentation published beside it.
function keyFingerprint(): string | null {
  try {
    const key = pinnedVerifierKey();
    const hex = Array.from(key.keyId, (b) => b.toString(16).padStart(2, "0")).join("");
    return `${key.name} · ${hex}`;
  } catch {
    return null; // a local build without the key configured
  }
}

export function BuildFooter() {
  const info = buildInfo();
  const fingerprint = keyFingerprint();
  return (
    <footer className="border-t border-border bg-bg-elevated">
      <div className="mx-auto flex max-w-[1200px] flex-wrap items-center gap-x-6 gap-y-2 px-[var(--gutter)] py-5 text-xs text-fg-muted">
        {info && (
          <span>
            Built from commit{" "}
            {info.url ? (
              <a
                href={info.url}
                className="font-mono text-accent underline-offset-4 hover:underline"
                title={info.commit}
              >
                {info.short}
              </a>
            ) : (
              <span className="font-mono" title={info.commit}>
                {info.short}
              </span>
            )}
          </span>
        )}
        {fingerprint && (
          <span className="breakable">
            Pinned key <span className="font-mono">{fingerprint}</span>
          </span>
        )}
        <a href={docsPath()} className="text-accent underline-offset-4 hover:underline">
          Read the documentation
        </a>
      </div>
    </footer>
  );
}
