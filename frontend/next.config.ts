import type { NextConfig } from "next";

// The public demo is a static export: no server, nothing that can sleep or expire.
// Every proof is verified in the browser from the bundled data.
// On GitHub Pages the site lives under /<repository>/, set through NEXT_PUBLIC_BASE_PATH.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const config: NextConfig = {
  output: "export",
  basePath,
  reactStrictMode: true,
  trailingSlash: true,
  images: { unoptimized: true },
};

export default config;
