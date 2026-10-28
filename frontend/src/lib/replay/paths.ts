/**
 * Where the signed replay bundle is served from.
 *
 * An explicit NEXT_PUBLIC_REPLAY_BASE wins. Otherwise the bundle sits under the
 * site's base path, which is empty locally and the repository name on GitHub Pages.
 */
export function replayBase(): string {
  const configured = process.env.NEXT_PUBLIC_REPLAY_BASE;
  if (configured) {
    return configured.replace(/\/+$/, "");
  }
  return `${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/replay`;
}
