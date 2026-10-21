import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "@/app/api/auth/resend/route";
import { PENDING_EMAIL_COOKIE, SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const ME = {
  id: "u1",
  email: "signed-in@example.com",
  email_verified: false,
  timezone: "Asia/Ho_Chi_Minh",
  day_start_hour: 4,
};

describe("POST /api/auth/resend (T1.13, AC2)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it("F1: resends to the email remembered at sign-up", async () => {
    const calls = fakeCoreApi(() => Response.json({ status: "check_email" }, { status: 202 }));

    const response = await POST(
      browserPost("/api/auth/resend", undefined, {
        cookies: { [PENDING_EMAIL_COOKIE]: encodeURIComponent("minhanh@sv.edu.vn") },
      }),
    );

    expect(response.status).toBe(200);
    expect(calls.map((c) => [c.path, c.body])).toEqual([
      ["/v1/auth/verify-email/resend", { email: "minhanh@sv.edu.vn" }],
    ]);
  });

  it("F1: a signed-in, unverified user gets it at the account's email", async () => {
    const calls = fakeCoreApi((call) =>
      call.path === "/v1/me" ? Response.json(ME) : Response.json({}, { status: 202 }),
    );

    await POST(
      browserPost("/api/auth/resend", undefined, {
        cookies: { [SESSION_COOKIE]: "tok", [PENDING_EMAIL_COOKIE]: "other%40example.com" },
      }),
    );

    expect(calls.at(-1)?.body).toEqual({ email: ME.email });
  });

  it("takes no email from the request body", async () => {
    const calls = fakeCoreApi(() => Response.json({}, { status: 202 }));

    const response = await POST(browserPost("/api/auth/resend", { email: "victim@example.com" }));

    expect(response.status).toBe(400);
    expect(calls).toHaveLength(0);
  });

  it("AC2, F3: 429 passes Retry-After through, so the countdown restarts from it", async () => {
    fakeCoreApi(() =>
      Response.json({ detail: "rate_limited" }, { status: 429, headers: { "retry-after": "42" } }),
    );

    const response = await POST(
      browserPost("/api/auth/resend", undefined, {
        cookies: { [PENDING_EMAIL_COOKIE]: "a%40example.com" },
      }),
    );

    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("42");
  });

  it("ADR-0014: a POST from another site is refused before core-api is called", async () => {
    const calls = fakeCoreApi(() => Response.json({}, { status: 202 }));

    const response = await POST(
      browserPost("/api/auth/resend", undefined, {
        origin: "https://evil.example",
        cookies: { [PENDING_EMAIL_COOKIE]: "a%40example.com" },
      }),
    );

    expect(response.status).toBe(403);
    expect(calls).toHaveLength(0);
  });
});
