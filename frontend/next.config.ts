import type { NextConfig } from "next";

// The public demo is a static export: no server, nothing that can sleep or expire.
// Every proof is verified in the browser from the bundled data.
const config: NextConfig = {
  output: "export",
  reactStrictMode: true,
  trailingSlash: true,
  images: { unoptimized: true },
};

export default config;
