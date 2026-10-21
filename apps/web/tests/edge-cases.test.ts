import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as confirm } from "@/app/api/auth/password-reset/confirm/route";
import { POST as register } from "@/app/api/auth/register/route";
import { POST as resend } from "@/app/api/auth/resend/route";
import { clientIpFrom } from "@/lib/client-ip";
import { cookieOptions, PENDING_EMAIL_COOKIE } from "@/lib/cookies";
import { readStrings } from "@/lib/http";
import { THEME_KEY, THEME_SCRIPT } from "@/lib/theme";

import { browserPost, fakeCoreApi, SERVICE_TOKEN, setCookies } from "./helpers";

// Tester (bước 4): ca biên mà đột biến cho thấy chưa có test nào bắt.

const LINK_TOKEN = "reset-token-marker-edge-77";
const NEW_PASSWORD = "new-password-marker-edge-88";

describe("cookieOptions (W6, A2)", () => {
  it("never gives a negative Max-Age when the session already ended (bỏ Math.max(0, …) thì đỏ)", () => {
    const now = new Date("2026-10-21T00:00:00Z");
    expect(cookieOptions(new Date("2026-10-20T00:00:00Z"), now).maxAge).toBe(0);
    expect(cookieOptions(now, now).maxAge).toBe(0);
  });

  it("rounds a part of a second down (đổi floor thành ceil thì đỏ)", () => {
    const now = new Date("2026-10-21T00:00:00.000Z");
    expect(cookieOptions(new Date("2026-10-21T00:00:10.900Z"), now).maxAge).toBe(10);
  });
});

describe("theme storage key (W11)", () => {
  it("stays 'essity-theme': changing it would forget every user's choice", () => {
    expect(THEME_KEY).toBe("essity-theme");
    expect(THEME_SCRIPT).toContain('localStorage.getItem("essity-theme")');
  });
});

describe("readStrings boundary of 8 KB (review cdbaa25 #3)", () => {
  const LIMIT = 8 * 1024;
  function bodyOfBytes(total: number): string {
    const base = JSON.stringify({ email: "" });
    return JSON.stringify({ email: "x".repeat(total - base.length) });
  }
  function post(body: string) {
    return new Request("http://localhost:3000/x", { method: "POST", body });
  }

  it("accepts a body of exactly 8192 bytes and refuses 8193 (đổi > thành >= hoặc đổi hằng số thì đỏ)", async () => {
    expect(await readStrings(post(bodyOfBytes(LIMIT)), ["email"])).not.toBeNull();
    expect(await readStrings(post(bodyOfBytes(LIMIT + 1)), ["email"])).toBeNull();
  });

  it("refuses by Content-Length alone, before reading", async () => {
    const request = new Request("http://localhost:3000/x", {
      method: "POST",
      body: '{"email":"a"}',
      headers: { "content-length": String(LIMIT + 1) },
    });
    expect(await readStrings(request, ["email"])).toBeNull();
  });

  it("ignores extra fields and keeps only the named ones", async () => {
    expect(await readStrings(post('{"email":"a","role":"admin"}'), ["email"])).toEqual({ email: "a" });
  });
});

describe("clientIpFrom malformed X-Forwarded-For (W4)", () => {
  const xff = (value: string) => new Headers({ "x-forwarded-for": value });

  it("is null without the header even behind a trusted proxy", () => {
    expect(clientIpFrom(new Headers(), 1)).toBeNull();
  });

  it.each(["203.0.113.7, ", "203.0.113.7,,", ",", "203.0.113.7:443", "203.0.113.7/24", "unknown"])(
    "does not take %j as the user's IP",
    (value) => {
      expect(clientIpFrom(xff(value), 1)).toBeNull();
    },
  );

  it("trims spaces around the entry and counts from the right with two proxies", () => {
    expect(clientIpFrom(xff("6.6.6.6 ,  203.0.113.7 ,10.0.0.1"), 2)).toBe("203.0.113.7");
  });

  it("has no hop to trust when the list is exactly one shorter than the hops", () => {
    expect(clientIpFrom(xff("10.0.0.1"), 2)).toBeNull();
  });
});

describe("POST /api/auth/password-reset/confirm failures (AC6, ADR-0013)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it("AC6: 429 passes Retry-After on, so the form keeps the token and shows the wait (bỏ nhánh 429 thì đỏ)", async () => {
    fakeCoreApi(() =>
      Response.json({ detail: "rate_limited" }, { status: 429, headers: { "retry-after": "321" } }),
    );

    const response = await confirm(
      browserPost("/api/auth/password-reset/confirm", { token: LINK_TOKEN, password: NEW_PASSWORD }),
    );

    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("321");
    expect(await response.json()).toEqual({ error: "rate_limited" });
  });

  it.each([
    ["core-api 500", () => new Response(null, { status: 500 })],
    [
      "core-api unreachable",
      () => {
        throw new TypeError("fetch failed");
      },
    ],
  ])("is 'unavailable' (not 'expired') on %s, and logs neither token nor password", async (_n, reply) => {
    const logged: unknown[] = [];
    for (const level of ["error", "warn", "log", "info"] as const) {
      vi.spyOn(console, level).mockImplementation((...args) => logged.push(...args));
    }
    fakeCoreApi(reply);

    const response = await confirm(
      browserPost("/api/auth/password-reset/confirm", { token: LINK_TOKEN, password: NEW_PASSWORD }),
    );

    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ error: "unavailable" });
    expect(JSON.stringify(logged)).not.toContain(LINK_TOKEN);
    expect(JSON.stringify(logged)).not.toContain(NEW_PASSWORD);
  });

  it("does not clear the session cookie when the reset failed", async () => {
    fakeCoreApi(() => Response.json({ detail: "invalid_or_expired_token" }, { status: 400 }));

    const response = await confirm(
      browserPost(
        "/api/auth/password-reset/confirm",
        { token: LINK_TOKEN, password: NEW_PASSWORD },
        { cookies: { "__Host-essity_session": "tok" } },
      ),
    );

    expect(setCookies(response).size).toBe(0);
  });
});

describe("pending sign-up email (F1)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it("is not remembered when core-api failed (đặt cookie ngoài nhánh 202 thì đỏ)", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    fakeCoreApi(() => new Response(null, { status: 500 }));

    const response = await register(
      browserPost("/api/auth/register", { email: "a@example.com", password: "password-marker-edge" }),
    );

    expect(response.status).toBe(503);
    expect(setCookies(response).size).toBe(0);
  });

  it("survives the cookie round trip for an address with + and other reserved characters", async () => {
    const email = "ten+lop@sv.edu.vn";
    fakeCoreApi(() => Response.json({ status: "check_email" }, { status: 202 }));
    const registered = await register(
      browserPost("/api/auth/register", { email, password: "password-marker-edge" }),
    );
    const line = setCookies(registered).get(PENDING_EMAIL_COOKIE) ?? "";
    const value = line.slice(line.indexOf("=") + 1, line.indexOf(";"));

    const calls = fakeCoreApi(() => Response.json({ status: "check_email" }, { status: 202 }));
    await resend(
      browserPost("/api/auth/resend", undefined, { cookies: { [PENDING_EMAIL_COOKIE]: value } }),
    );

    expect(calls[0].body).toEqual({ email });
  });

  it("resend without session or cookie asks core-api nothing", async () => {
    const calls = fakeCoreApi(() => Response.json({}, { status: 202 }));

    const response = await resend(browserPost("/api/auth/resend"));

    expect(response.status).toBe(400);
    expect(calls).toHaveLength(0);
  });

  it("resend ignores an email in the body (no mailing a stranger)", async () => {
    const calls = fakeCoreApi(() => Response.json({}, { status: 202 }));

    const response = await resend(browserPost("/api/auth/resend", { email: "victim@example.com" }));

    expect(response.status).toBe(400);
    expect(calls).toHaveLength(0);
  });
});
