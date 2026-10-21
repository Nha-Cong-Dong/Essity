import path from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  output: "standalone",
  // Pages opened from a link carrying a one-time token: no Referer leaves them (PLAN T1.13).
  async headers() {
    return ["/verify-email", "/reset-password"].map((source) => ({
      source,
      headers: [{ key: "Referrer-Policy", value: "no-referrer" }],
    }));
  },
  // Monorepo: trace dependencies from the repo root so the standalone build includes them.
  outputFileTracingRoot: path.join(__dirname, "../.."),
  turbopack: {
    rules: {
      "*.css": {
        // CSS Modules (components/**/*.module.css) are plain CSS: leave them to Next, which
        // scopes their class names. Run through Tailwind they lose their exports.
        condition: { not: { path: "*.module.css" } },
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
