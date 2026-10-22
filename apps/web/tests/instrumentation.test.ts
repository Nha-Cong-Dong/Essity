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

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

/** process.exit, stopped so the test run goes on; it throws like a real exit would end. */
function spyOnExit() {
  return vi.spyOn(process, "exit").mockImplementation((code) => {
    throw new Error(`exit:${code}`);
  });
}

describe("register (R04)", () => {
  // Red when: register() only throws. Next logs "Failed to prepare server" and keeps serving
  // 500s (checked by hand on the standalone build, review 3882431), so it must end the process.
  it("ends the process without CORE_API_URL in production, naming it", async () => {
    stub({ ...PRODUCTION, CORE_API_URL: undefined });
    const exit = spyOnExit();
    const logged = vi.spyOn(console, "error").mockImplementation(() => undefined);
    await expect(register()).rejects.toThrow("exit:1");
    expect(exit).toHaveBeenCalledWith(1);
    expect(String(logged.mock.calls[0])).toMatch(/CORE_API_URL/);
  });

  it("never prints a setting's value", async () => {
    stub({ ...PRODUCTION, WEB_TO_CORE_TOKEN: "short-secret-value" });
    spyOnExit();
    const logged = vi.spyOn(console, "error").mockImplementation(() => undefined);
    await expect(register()).rejects.toThrow("exit:1");
    expect(JSON.stringify(logged.mock.calls)).not.toContain("short-secret-value");
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
