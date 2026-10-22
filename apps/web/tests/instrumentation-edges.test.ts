// R04 edge found by the Tester (feature-tester, 23/10): register() names the variable for a
// WebConfigError, but an error of any other kind (a bug, a library failure) may quote a value.
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/instrumentation.node", () => ({}));
vi.mock("@/lib/config", async (original) => ({
  ...(await original<typeof import("@/lib/config")>()),
  webConfig: () => {
    throw new TypeError("Invalid URL: https://user:hunter2-secret@core-api/");
  },
}));

const { register } = await import("@/instrumentation");

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("register with an error that is not a WebConfigError (R04)", () => {
  // Red when: the log line prints `String(error)` / `error.message` for any error: a value from
  // the environment (here a password inside a URL) would reach the logs.
  it("exits 1 and logs a fixed sentence, not the error's text", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_RUNTIME", "nodejs");
    vi.stubEnv("NEXT_PHASE", "");
    vi.spyOn(process, "exit").mockImplementation((code) => {
      throw new Error(`exit:${code}`);
    });
    const logged = vi.spyOn(console, "error").mockImplementation(() => undefined);
    await expect(register()).rejects.toThrow("exit:1");
    const output = JSON.stringify(logged.mock.calls);
    expect(output).toContain("invalid settings");
    expect(output).not.toMatch(/hunter2|Invalid URL/);
  });

  // Red when: the NEXT_RUNTIME guard is removed and the Edge runtime (no process.exit, no
  // node:* modules) runs the check.
  it("does nothing outside the Node.js runtime", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_RUNTIME", "edge");
    const exit = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
    await expect(register()).resolves.toBeUndefined();
    expect(exit).not.toHaveBeenCalled();
  });
});
