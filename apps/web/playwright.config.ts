import { randomBytes } from "node:crypto";

import { defineConfig } from "@playwright/test";

// ADR-0025: layout tests on the production build (standalone server), against
// /design-preview/subjects. Run `pnpm build` and `node scripts/prepare-standalone.mjs` first;
// a server already listening is never reused, so a dev server or an old build cannot answer.
const PORT = 3100;
const ORIGIN = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  workers: process.env.CI ? 2 : 1,
  // A flaky layout test is a bug to find, not to retry past (risk register R43).
  retries: 0,
  reporter: "list",
  use: { baseURL: ORIGIN, browserName: "chromium", screenshot: "only-on-failure" },
  webServer: {
    command: "node .next/standalone/apps/web/server.js",
    url: `${ORIGIN}/design-preview/subjects`,
    reuseExistingServer: false,
    timeout: 60_000,
    env: {
      PORT: String(PORT),
      HOSTNAME: "127.0.0.1",
      NODE_ENV: "production",
      WEB_DESIGN_PREVIEW: "1",
      WEB_ORIGIN: ORIGIN,
      // Throwaway, made per run: nothing calls core-api here (port 9 refuses at once).
      WEB_TO_CORE_TOKEN: randomBytes(24).toString("hex"),
      WEB_TRUSTED_PROXY_HOPS: "0",
      CORE_API_URL: "http://127.0.0.1:9",
    },
  },
});
