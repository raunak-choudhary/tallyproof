import { describe, expect, it } from "vitest";

import { buildInfo, docsPath } from "./info";

const SHA = "94c93cb5d1e0f2a3b4c5d6e7f8091a2b3c4d5e6f";

describe("buildInfo", () => {
  it("links the exact commit the site was built from", () => {
    expect(buildInfo(SHA, "https://github.com/owner/repo/")).toEqual({
      commit: SHA,
      short: "94c93cb",
      url: `https://github.com/owner/repo/tree/${SHA}`,
    });
  });

  it("shows the commit without a link when no source URL was given", () => {
    expect(buildInfo(SHA, "")?.url).toBeNull();
  });

  it("shows nothing for a local build or a value that isn't a commit", () => {
    expect(buildInfo(undefined, undefined)).toBeNull();
    expect(buildInfo("main", "https://github.com/owner/repo")).toBeNull();
  });
});

describe("docsPath", () => {
  it("puts the docs under the site's base path", () => {
    expect(docsPath("/tallyproof")).toBe("/tallyproof/docs/");
    expect(docsPath("/tallyproof/")).toBe("/tallyproof/docs/");
    expect(docsPath("")).toBe("/docs/");
    expect(docsPath(undefined)).toBe("/docs/");
  });
});
