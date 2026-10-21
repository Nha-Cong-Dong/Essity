import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "@/app/api/auth/register/route";
import { PENDING_EMAIL_COOKIE, SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN, setCookies } from "../helpers";

const SIGN_UP = { email: "minhanh@sv.edu.vn", password: "password-marker-7a3b" };

describe("POST /api/auth/register (T1.13)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it("AC1: sends exactly the two fields to core-api", async () => {
    const calls = fakeCoreApi(() => Response.json({ status: "check_email" }, { status: 202 }));

    await POST(browserPost("/api/auth/register", { ...SIGN_UP, extra: "ignored" }));

    expect(calls[0].path).toBe("/v1/auth/register");
    expect(calls[0].body).toEqual(SIGN_UP);
  });

  it("AC5: always goes to /check-email on 202, whether or not the account existed", async () => {
    fakeCoreApi(() => Response.json({ status: "check_email" }, { status: 202 }));

    const response = await POST(browserPost("/api/auth/register", SIGN_UP));

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ next: "/check-email" });
  });

  it("F1: remembers the email for /check-email in a 24-hour HttpOnly cookie, never in the URL", async () => {
    fakeCoreApi(() => Response.json({ status: "check_email" }, { status: 202 }));

    const response = await POST(browserPost("/api/auth/register", SIGN_UP));

    const cookie = setCookies(response).get(PENDING_EMAIL_COOKIE) ?? "";
    expect(PENDING_EMAIL_COOKIE).toBe("__Host-essity_pending_email");
    expect(cookie).toContain(encodeURIComponent(SIGN_UP.email));
    expect(cookie).toMatch(/Max-Age=86400/i);
    expect(cookie).toMatch(/; HttpOnly/i);
    expect(cookie).toMatch(/; Secure/i);
    expect(cookie).toMatch(/; SameSite=Lax/i);
    expect(cookie).toMatch(/; Path=\/(;|$)/);
    expect(setCookies(response).has(SESSION_COOKIE)).toBe(false);
  });

  it.each(["too_short", "too_long", "common", "same_as_email"])(
    "AC1: a password refused as %s comes back with its reason and no cookie",
    async (reason) => {
      fakeCoreApi(() => Response.json({ detail: reason }, { status: 422 }));

      const response = await POST(browserPost("/api/auth/register", SIGN_UP));

      expect(response.status).toBe(422);
      expect(await response.json()).toEqual({ error: reason });
      expect(setCookies(response).size).toBe(0);
    },
  );

  it("a malformed email is invalid_email", async () => {
    fakeCoreApi(() =>
      Response.json({ detail: [{ loc: ["body", "email"], type: "value_error" }] }, { status: 422 }),
    );

    const response = await POST(browserPost("/api/auth/register", SIGN_UP));

    expect(await response.json()).toEqual({ error: "invalid_email" });
  });

  it("an unknown 422 reason is not passed through as is", async () => {
    fakeCoreApi(() => Response.json({ detail: "something_new" }, { status: 422 }));

    const response = await POST(browserPost("/api/auth/register", SIGN_UP));

    expect(await response.json()).toEqual({ error: "invalid_password" });
  });

  it("AC6: 429 passes Retry-After through", async () => {
    fakeCoreApi(() =>
      Response.json({ detail: "rate_limited" }, { status: 429, headers: { "retry-after": "3000" } }),
    );

    const response = await POST(browserPost("/api/auth/register", SIGN_UP));

    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("3000");
  });

  it("AC8: the response never echoes the password", async () => {
    fakeCoreApi(() => Response.json({ detail: "common" }, { status: 422 }));

    const response = await POST(browserPost("/api/auth/register", SIGN_UP));

    expect(await response.text()).not.toContain(SIGN_UP.password);
  });

  it("ADR-0014: a POST from another site is refused before core-api is called", async () => {
    const calls = fakeCoreApi(() => Response.json({}, { status: 202 }));

    const response = await POST(
      browserPost("/api/auth/register", SIGN_UP, { origin: "https://evil.example" }),
    );

    expect(response.status).toBe(403);
    expect(calls).toHaveLength(0);
  });
});
