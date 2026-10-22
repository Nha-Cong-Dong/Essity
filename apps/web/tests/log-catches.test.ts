// Risk register R12: the two failures web recovers from on its own are logged (status and the
// error's type only), so an outage behind them shows up in the logs.
import { afterEach, describe, expect, it, vi } from "vitest";

const logError = vi.fn();
vi.mock("@/lib/log", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/log")>()),
  logError: (...args: unknown[]) => logError(...args),
}));
vi.mock("next/server", () => ({ connection: async () => undefined }));
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw new Error(`redirect:${to}`);
  },
}));
let session: () => Promise<unknown> = async () => null;
vi.mock("@/lib/session", () => ({ getSession: () => session() }));

const { nextAfterBaseline } = await import("@/lib/onboarding");
const { RedirectIfSignedIn } = await import("@/components/auth/redirect-if-signed-in");

afterEach(() => logError.mockReset());

describe("recovered failures are logged (R12)", () => {
  // Red when: the catch in nextAfterBaseline still swallows the error silently.
  it("/v1/me failing after a baseline save", async () => {
    const core = { GET: async () => Promise.reject(new TypeError("fetch failed: secret-host")) };
    expect(await nextAfterBaseline(core as never)).toBe("/today");
    expect(logError).toHaveBeenCalledWith("core-api call failed", { route: "baseline-next", error: "TypeError" });
  });

  // Red when: getSession().catch(() => null) still hides a core-api outage on /login.
  it("core-api failing behind /login and /register", async () => {
    session = async () => Promise.reject(new Error("core-api answered /v1/me with 503"));
    expect(await RedirectIfSignedIn()).toBeNull();
    expect(logError).toHaveBeenCalledWith("core-api call failed", { route: "session-check", error: "Error" });
  });

  it("logs nothing when there is simply no session", async () => {
    session = async () => null;
    expect(await RedirectIfSignedIn()).toBeNull();
    expect(logError).not.toHaveBeenCalled();
  });
});
