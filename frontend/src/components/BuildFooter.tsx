import { buildInfo } from "@/lib/release/info";

// Names the commit the site was built from, so anyone can check the code that
// verified their proof. Local builds have no commit and show nothing.
export function BuildFooter() {
  const info = buildInfo();
  if (!info) {
    return null;
  }
  return (
    <footer className="mx-auto max-w-3xl px-4 pb-10 text-xs text-fg-muted md:px-8">
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
      .
    </footer>
  );
}
