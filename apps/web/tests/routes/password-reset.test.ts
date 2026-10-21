import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as confirm } from "@/app/api/auth/password-reset/confirm/route";
import { POST as request } from "@/app/api/auth/password-reset/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN, setCookies } from "../helpers";

const LINK_TOKEN = "reset-token-marker-6e1f";
const NEW_PASSWORD = "new-password-marker-2b9c";

describe("POST /api/auth/password-reset (T1.14)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it("asks core-api to mail a reset link, with the user's IP rules applied there", async () => {
    const calls = fakeCoreApi(() => Response.json({ status: "check_email" }, { status: 202 }));

    const response = await request(browserPost("/api/auth/password-reset", { email: "a@example.com" }));

    expect(calls.map((c) => [c.path, c.body])).toEqual([
      ["/v1/auth/password-reset", { email: "a@example.com" }],
    ]);
    expect(calls[0].headers.get("x-service-token")).toBe(SERVICE_TOKEN);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "sent" });
  });

  it("AC5: a malformed email gets the same answer as any other (nothing to learn)", async () => {
    fakeCoreApi(() => Response.json({ detail: [{ loc: ["body", "email"] }] }, { status: 422 }));

    const response = await request(browserPost("/api/auth/password-reset", { email: "nope" }));

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "sent" });
  });

  it("AC6: 429 passes Retry-After through", async () => {
    fakeCoreApi(() =>
      Response.json({ detail: "rate_limited" }, { status: 429, headers: { "retry-after": "600" } }),
    );

    const response = await request(browserPost("/api/auth/password-reset", { email: "a@example.com" }));

    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("600");
  });

  it("ADR-0014: a POST from another site is refused before core-api is called", async () => {
    const calls = fakeCoreApi(() => Response.json({}, { status: 202 }));

    const response = await request(
      browserPost("/api/auth/password-reset", { email: "a@example.com" }, { origin: "https://evil.example" }),
    );

    expect(response.status).toBe(403);
    expect(calls).toHaveLength(0);
  });
});

describe("POST /api/auth/password-reset/confirm (T1.14)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it("sends the link's token and the new password to core-api", async () => {
    const calls = fakeCoreApi(() => Response.json({ status: "password_reset" }));

    const response = await confirm(
      browserPost("/api/auth/password-reset/confirm", { token: LINK_TOKEN, password: NEW_PASSWORD }),
    );

    expect(calls.map((c) => [c.path, c.body])).toEqual([
      ["/v1/auth/password-reset/confirm", { token: LINK_TOKEN, password: NEW_PASSWORD }],
    ]);
    expect(await response.json()).toEqual({ done: true });
  });

  it("AC4, F6: clears this browser's session cookie too (core-api revoked every session)", async () => {
    fakeCoreApi(() => Response.json({ status: "password_reset" }));

    const response = await confirm(
      browserPost(
        "/api/auth/password-reset/confirm",
        { token: LINK_TOKEN, password: NEW_PASSWORD },
        { cookies: { [SESSION_COOKIE]: "tok" } },
      ),
    );

    expect(setCookies(response).get(SESSION_COOKIE)).toMatch(/Max-Age=0/i);
  });

  it.each(["too_short", "common", "same_as_email"])(
    "AC1, F6: a refused password (%s) keeps the link usable: its reason, not 'expired'",
    async (reason) => {
      fakeCoreApi(() => Response.json({ detail: reason }, { status: 422 }));

      const response = await confirm(
        browserPost("/api/auth/password-reset/confirm", { token: LINK_TOKEN, password: "x" }),
      );

      expect(response.status).toBe(422);
      expect(await response.json()).toEqual({ error: reason });
    },
  );

  it.each([
    ["a malformed token (field errors)", { detail: [{ loc: ["body", "token"] }] }, 400, "invalid_or_expired_token"],
    // Over core-api's 1024-character cap: the link still works (review bb28275 #1).
    ["a password too long for the field", { detail: [{ loc: ["body", "password"] }] }, 422, "too_long"],
    [
      "both fields refused",
      { detail: [{ loc: ["body", "token"] }, { loc: ["body", "password"] }] },
      400,
      "invalid_or_expired_token",
    ],
    ["a reason web does not know", { detail: "something_new" }, 422, "invalid_password"],
  ])("F6: 422 for %s (review 7ea491c #1)", async (_name, detail, status, error) => {
    fakeCoreApi(() => Response.json(detail, { status: 422 }));

    const response = await confirm(
      browserPost("/api/auth/password-reset/confirm", { token: LINK_TOKEN, password: NEW_PASSWORD }),
    );

    expect(response.status).toBe(status);
    expect(await response.json()).toEqual({ error });
  });

  it("AC4, F6: an expired or used link is invalid_or_expired_token", async () => {
    fakeCoreApi(() => Response.json({ detail: "invalid_or_expired_token" }, { status: 400 }));

    const response = await confirm(
      browserPost("/api/auth/password-reset/confirm", { token: LINK_TOKEN, password: NEW_PASSWORD }),
    );

    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "invalid_or_expired_token" });
  });

  it("AC8: never echoes the token or the password", async () => {
    fakeCoreApi(() => Response.json({ detail: "common" }, { status: 422 }));

    const response = await confirm(
      browserPost("/api/auth/password-reset/confirm", { token: LINK_TOKEN, password: NEW_PASSWORD }),
    );

    const body = await response.text();
    expect(body).not.toContain(LINK_TOKEN);
    expect(body).not.toContain(NEW_PASSWORD);
  });

  it("ADR-0014: a POST from another site is refused before core-api is called", async () => {
    const calls = fakeCoreApi(() => Response.json({}));

    const response = await confirm(
      browserPost(
        "/api/auth/password-reset/confirm",
        { token: LINK_TOKEN, password: NEW_PASSWORD },
        { origin: "https://evil.example" },
      ),
    );

    expect(response.status).toBe(403);
    expect(calls).toHaveLength(0);
  });
});
