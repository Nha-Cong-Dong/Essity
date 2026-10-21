import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "@/app/api/auth/login/route";
import { PENDING_EMAIL_COOKIE, SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN, setCookies } from "../helpers";

const CREDENTIALS = { email: "a@example.com", password: "password-marker-5f1c" };
const SESSION_TOKEN = "session-token-marker-9d2e";

function loginOk({ verified = true, expiresInSeconds = 90 * 24 * 3600 } = {}) {
  return fakeCoreApi(() =>
    Response.json({
      token: SESSION_TOKEN,
      expires_at: new Date(Date.now() + expiresInSeconds * 1000).toISOString(),
      email_verified: verified,
    }),
  );
}

describe("POST /api/auth/login (T1.12)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it("forwards the credentials to core-api with the service token", async () => {
    const calls = loginOk();

    await POST(browserPost("/api/auth/login", CREDENTIALS));

    expect(calls).toHaveLength(1);
    expect(calls[0].path).toBe("/v1/auth/login");
    expect(calls[0].body).toEqual(CREDENTIALS);
    expect(calls[0].headers.get("x-service-token")).toBe(SERVICE_TOKEN);
  });

  it("ADR-0014: sets the session cookie HttpOnly, Secure, SameSite=Lax, host-only, Path=/", async () => {
    loginOk();

    const response = await POST(browserPost("/api/auth/login", CREDENTIALS));

    expect(SESSION_COOKIE).toBe("__Host-essity_session");
    const cookie = setCookies(response).get(SESSION_COOKIE) ?? "";
    expect(cookie).toContain(`${SESSION_COOKIE}=${SESSION_TOKEN}`);
    expect(cookie).toMatch(/; HttpOnly/i);
    expect(cookie).toMatch(/; Secure/i);
    expect(cookie).toMatch(/; SameSite=Lax/i);
    expect(cookie).toMatch(/; Path=\/(;|$)/);
    expect(cookie).not.toMatch(/Domain=/i);
  });

  it("A2, AC7: the cookie lives exactly as long as the session's cap", async () => {
    loginOk({ expiresInSeconds: 3600 });

    const response = await POST(browserPost("/api/auth/login", CREDENTIALS));

    const maxAge = Number(/Max-Age=(\d+)/i.exec(setCookies(response).get(SESSION_COOKIE) ?? "")?.[1]);
    expect(maxAge).toBeGreaterThan(3590);
    expect(maxAge).toBeLessThanOrEqual(3600);
  });

  it("AC8: the token never reaches the browser's JavaScript (not in the body)", async () => {
    loginOk();

    const response = await POST(browserPost("/api/auth/login", CREDENTIALS));

    const body = await response.text();
    expect(body).not.toContain(SESSION_TOKEN);
    expect(body).not.toContain(CREDENTIALS.password);
  });

  it("AC7: a verified user goes to /today", async () => {
    loginOk({ verified: true });

    const response = await POST(browserPost("/api/auth/login", CREDENTIALS));

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ next: "/today" });
  });

  it("AC2: an unverified user goes to /check-email", async () => {
    loginOk({ verified: false });

    const response = await POST(browserPost("/api/auth/login", CREDENTIALS));

    expect(await response.json()).toEqual({ next: "/check-email" });
  });

  it("clears a pending sign-up email once signed in", async () => {
    loginOk();

    const response = await POST(
      browserPost("/api/auth/login", CREDENTIALS, {
        cookies: { [PENDING_EMAIL_COOKIE]: "a%40example.com" },
      }),
    );

    expect(setCookies(response).get(PENDING_EMAIL_COOKIE)).toMatch(/Max-Age=0/i);
  });

  it.each([
    ["wrong credentials (401)", 401, { detail: "invalid_credentials" }],
    ["a malformed email (422)", 422, { detail: [{ loc: ["body", "email"] }] }],
  ])("AC5: %s gives the one sentence's code and no cookie", async (_name, status, detail) => {
    fakeCoreApi(() => Response.json(detail, { status }));

    const response = await POST(browserPost("/api/auth/login", CREDENTIALS));

    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ error: "invalid_credentials" });
    expect(setCookies(response).has(SESSION_COOKIE)).toBe(false);
  });

  it("AC6: 429 passes Retry-After through, with no count of attempts left", async () => {
    fakeCoreApi(() =>
      Response.json({ detail: "rate_limited" }, { status: 429, headers: { "retry-after": "840" } }),
    );

    const response = await POST(browserPost("/api/auth/login", CREDENTIALS));

    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("840");
    expect(await response.json()).toEqual({ error: "rate_limited" });
  });

  it.each([
    ["core-api fails (503)", () => new Response(null, { status: 503 })],
    [
      "core-api cannot be reached",
      () => {
        throw new TypeError("fetch failed");
      },
    ],
  ])("never says 'wrong password' when %s", async (_name, reply) => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    fakeCoreApi(reply);

    const response = await POST(browserPost("/api/auth/login", CREDENTIALS));

    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ error: "unavailable" });
  });

  it("refuses a body that is not an email and a password", async () => {
    const calls = fakeCoreApi(() => new Response(null, { status: 500 }));

    const response = await POST(browserPost("/api/auth/login", { email: 1 }));

    expect(response.status).toBe(400);
    expect(calls).toHaveLength(0);
  });

  it("ADR-0014: a POST from another site is refused before core-api is called", async () => {
    const calls = loginOk();

    const response = await POST(
      browserPost("/api/auth/login", CREDENTIALS, { origin: "https://evil.example" }),
    );

    expect(response.status).toBe(403);
    expect(calls).toHaveLength(0);
  });

  it("ADR-0013, AC8: logs neither the password nor the session token", async () => {
    const logged: unknown[] = [];
    for (const level of ["log", "info", "warn", "error", "debug"] as const) {
      vi.spyOn(console, level).mockImplementation((...args) => logged.push(...args));
    }
    loginOk();
    await POST(browserPost("/api/auth/login", CREDENTIALS));
    fakeCoreApi(() => {
      throw new TypeError("fetch failed");
    });
    await POST(browserPost("/api/auth/login", CREDENTIALS));

    const text = JSON.stringify(logged, (_k, v) => (v instanceof Error ? String(v) : v));
    expect(text).not.toContain(CREDENTIALS.password);
    expect(text).not.toContain(SESSION_TOKEN);
  });
});
