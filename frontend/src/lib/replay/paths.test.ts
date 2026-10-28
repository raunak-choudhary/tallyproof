import { afterEach, describe, expect, it, vi } from "vitest";

import { replayBase } from "./paths";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("replayBase", () => {
  it("serves the bundle from the site root by default", () => {
    vi.stubEnv("NEXT_PUBLIC_REPLAY_BASE", "");
    vi.stubEnv("NEXT_PUBLIC_BASE_PATH", "");
    expect(replayBase()).toBe("/replay");
  });

  it("follows the base path when the site is served from a subfolder", () => {
    vi.stubEnv("NEXT_PUBLIC_REPLAY_BASE", "");
    vi.stubEnv("NEXT_PUBLIC_BASE_PATH", "/tallyproof");
    expect(replayBase()).toBe("/tallyproof/replay");
  });

  it("uses an explicit location without a trailing slash", () => {
    vi.stubEnv("NEXT_PUBLIC_REPLAY_BASE", "https://cdn.example.org/replay/");
    expect(replayBase()).toBe("https://cdn.example.org/replay");
  });
});
