// Risk register R04, review plan P1: a production server missing its settings stops at start,
// naming the variable, instead of answering 500 to its first visitor.
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/instrumentation.node", () => ({}));

const { register } = await import("@/instrumentation");

const PRODUCTION = {
  NODE_ENV: "production",
  NEXT_RUNTIME: "nodejs",
  WEB_ORIGIN: "https://essity.example",
  WEB_TO_CORE_TOKEN: "web-token-for-tests-only-0123456789",
  WEB_TRUSTED_PROXY_HOPS: "1",
  CORE_API_URL: "http://core-api:8000",
};

function stub(env: Record<string, string | undefined>) {
  for (const [name, value] of Object.entries(env)) vi.stubEnv(name, value);
}

afterEach(() => vi.unstubAllEnvs());

describe("register (R04)", () => {
  // Red when: register() starts the server without checking webConfig.
  it("refuses to start without CORE_API_URL in production", async () => {
    stub({ ...PRODUCTION, CORE_API_URL: undefined });
    await expect(register()).rejects.toThrow(/CORE_API_URL/);
  });

  it("starts with a complete configuration", async () => {
    stub(PRODUCTION);
    await expect(register()).resolves.toBeUndefined();
  });

  // Red when: `next build` (NODE_ENV=production, none of the settings) fails on the check.
  it("does not check during next build", async () => {
    stub({ NODE_ENV: "production", NEXT_RUNTIME: "nodejs", NEXT_PHASE: "phase-production-build" });
    await expect(register()).resolves.toBeUndefined();
  });
});
