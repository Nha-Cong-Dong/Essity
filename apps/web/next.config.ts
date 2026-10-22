import path from "node:path";

import type { NextConfig } from "next";

function contentSecurityPolicy(production: boolean): string {
  return [
    "default-src 'self'",
    production ? "script-src 'self' 'unsafe-inline'" : "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:", // the paper grain is an SVG data: URL
    "font-src 'self'",
    production ? "connect-src 'self'" : "connect-src 'self' ws: wss:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  output: "standalone",
  async headers() {
    // Read here, not at module load, so tests can set it (NODE_ENV is fixed at build time).
    const production = process.env.NODE_ENV === "production";
    return [
      // Risk register R06, ADR-0023: every page. A static CSP with 'unsafe-inline': a nonce
      // cannot work with partial prerendering, and Next writes inline scripts of its own. Dev
      // adds eval and the reload socket. HSTS only in production, never pinned on localhost.
      {
        source: "/(.*)",
        headers: [
          { key: "Content-Security-Policy", value: contentSecurityPolicy(production) },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
          ...(production ? [{ key: "Strict-Transport-Security", value: "max-age=31536000" }] : []),
        ],
      },
      // Pages opened from a link carrying a one-time token: no Referer leaves them (PLAN T1.13).
      // After the rule above: for a key set twice, Next keeps the later one (plan D7).
      ...["/verify-email", "/reset-password"].map((source) => ({
        source,
        headers: [{ key: "Referrer-Policy", value: "no-referrer" }],
      })),
    ];
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
