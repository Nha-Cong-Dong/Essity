import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "@/app/api/auth/verify-email/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "../helpers";

// Tester T1.22: the edge of the verify-email route that the Coder's tests leave open (the other
// two edges tried, a spent link with a session and a 401 after verifying, were already caught by
// the 400/422 and the "/v1/me answering 500" tests in verify-email.test.ts).
describe("POST /api/auth/verify-email, T1.22 edges", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  // Red when: the first /v1/me (before the link is spent) is wrapped like the second one
  // (sessionUserOrNull), so its failure is swallowed and the token is burnt although the owner
  // cannot be proven.
  it("AC11: /v1/me failing BEFORE the token is spent answers 503 and never spends it", async () => {
    const calls = fakeCoreApi(async (call) => {
      if (call.path === "/v1/me") throw new TypeError("fetch failed");
      return Response.json({ status: "verified" });
    });

    const response = await POST(
      browserPost("/api/auth/verify-email", { token: "t" }, { cookies: { [SESSION_COOKIE]: "tok" } }),
    );

    expect(response.status).toBe(503);
    expect(calls.map((c) => c.path)).not.toContain("/v1/auth/verify-email");
  });
});
