// Risk register R12: the two failures web recovers from on its own are logged (status and the
// error's type only), so an outage behind them shows up in the logs.
import { afterEach, describe, expect, it, vi } from "vitest";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "./helpers";

const logError = vi.fn();
vi.mock("@/lib/log", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/log")>()),
  logError: (...args: unknown[]) => logError(...args),
}));
vi.mock("next/server", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/server")>()),
  connection: async () => undefined,
}));
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw new Error(`redirect:${to}`);
  },
}));
let session: () => Promise<unknown> = async () => null;
vi.mock("@/lib/session", () => ({ getSession: () => session() }));

const { nextAfterBaseline } = await import("@/lib/onboarding");
const { RedirectIfSignedIn } = await import("@/components/auth/redirect-if-signed-in");
const { POST: verifyEmail } = await import("@/app/api/auth/verify-email/route");
const { SESSION_COOKIE } = await import("@/lib/cookies");

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

describe("/v1/me after an email is verified (T1.22, review 9d51d23 #1, #2)", () => {
  const UNVERIFIED = { id: "u1", email: "a@example.com", email_verified: false, timezone: "UTC", day_start_hour: 4, has_subjects: false };

  /** core-api verifies the token; /v1/me answers `before`, then `after`. */
  function afterVerifying(after: () => Response) {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
    let asked = 0;
    fakeCoreApi(async (call) => {
      if (call.path !== "/v1/me") return Response.json({ status: "verified" });
      return asked++ === 0 ? Response.json(UNVERIFIED) : after();
    });
    return verifyEmail(browserPost("/api/auth/verify-email", { token: "t" }, { cookies: { [SESSION_COOKIE]: "tok" } }));
  }

  // Red when: the route swallows a core-api outage with .catch(() => null) and logs nothing.
  it("a thrown call is logged with its type only", async () => {
    await afterVerifying(() => {
      throw new TypeError("fetch failed: secret-host");
    });
    expect(logError).toHaveBeenCalledWith("core-api call failed", { route: "verify-email", error: "TypeError" });
    expect(JSON.stringify(logError.mock.calls)).not.toContain("secret-host");
  });

  // Red when: a 500 from /v1/me reads as "no session" and leaves no trace.
  it("a 500 is logged with its status", async () => {
    await afterVerifying(() => Response.json({ detail: "boom" }, { status: 500 }));
    expect(logError).toHaveBeenCalledWith("core-api call failed", { route: "verify-email", status: 500 });
  });

  it("a 401 (the session has ended) is not an error", async () => {
    await afterVerifying(() => Response.json({ detail: "unauthenticated" }, { status: 401 }));
    expect(logError).not.toHaveBeenCalled();
  });
});
