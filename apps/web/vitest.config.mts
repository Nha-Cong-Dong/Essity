import path from "node:path";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": import.meta.dirname,
      // `server-only` throws outside the react-server condition; tests run plain Node.
      "server-only": path.join(import.meta.dirname, "node_modules/server-only/empty.js"),
    },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.{ts,tsx}"],
    restoreMocks: true,
    unstubEnvs: true,
    unstubGlobals: true,
    // Risk register R43: with every worker loading jsdom at once, a test that takes 0.4 s alone
    // took up to 6.5 s, past the 5 s default. waitFor/findBy keep their own 1 s limit.
    testTimeout: 15_000,
    // Flaky web tests (main-nav, session-live) failed only when the machine was busy: vitest starts
    // one jsdom worker per core, and several lanes run suites at once, so each test slowed past its
    // limit. A fixed, smaller pool keeps one run from taking the whole CPU from the others.
    maxWorkers: 6,
  },
});
