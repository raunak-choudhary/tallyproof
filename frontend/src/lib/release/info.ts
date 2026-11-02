/** The commit this site was built from, when the build recorded one. */
export interface BuildInfo {
  commit: string;
  short: string;
  url: string | null;
}

export function buildInfo(
  commit: string | undefined = process.env.NEXT_PUBLIC_BUILD_COMMIT,
  repoUrl: string | undefined = process.env.NEXT_PUBLIC_SOURCE_URL,
): BuildInfo | null {
  if (!commit || !/^[0-9a-f]{7,40}$/.test(commit)) {
    return null;
  }
  const base = repoUrl?.replace(/\/+$/, "");
  return { commit, short: commit.slice(0, 7), url: base ? `${base}/tree/${commit}` : null };
}

/** Where the documentation site lives: beside the demo, under the same base path. */
export function docsPath(basePath: string | undefined = process.env.NEXT_PUBLIC_BASE_PATH): string {
  return `${(basePath ?? "").replace(/\/+$/, "")}/docs/`;
}

/** Where the published videos and diagrams live: beside the demo, under the same base path. */
export function mediaPath(
  file: string,
  basePath: string | undefined = process.env.NEXT_PUBLIC_BASE_PATH,
): string {
  return `${(basePath ?? "").replace(/\/+$/, "")}/media/${file}`;
}
