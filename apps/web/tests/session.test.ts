import { beforeEach, describe, expect, it, vi } from "vitest";

import { fakeCoreApi } from "./helpers";

const cookieJar = new Map<string, string>();
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      cookieJar.has(name) ? { name, value: cookieJar.get(name) as string } : undefined,
  }),
}));
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw new Error(`redirect:${to}`);
  },
}));

const { SESSION_COOKIE, getSession, requireSession, requireVerifiedSession } = await import(
  "@/lib/session"
);

const ME = {
  id: "u1",
  email: "a@example.com",
  email_verified: true,
  timezone: "Asia/Ho_Chi_Minh",
  day_start_hour: 4,
};

describe("session (T1.12, W3)", () => {
  beforeEach(() => {
    cookieJar.clear();
  });

  it("has no session and asks core-api nothing without a cookie", async () => {
    const calls = fakeCoreApi(() => Response.json(ME));

    expect(await getSession()).toBeNull();
    expect(calls).toHaveLength(0);
  });

  it("asks core-api who the cookie belongs to", async () => {
    cookieJar.set(SESSION_COOKIE, "tok");
    const calls = fakeCoreApi(() => Response.json(ME));

    expect(await getSession()).toEqual(ME);
    expect(calls[0].path).toBe("/v1/me");
    expect(calls[0].headers.get("authorization")).toBe("Bearer tok");
  });

  it("AC7: a cookie core-api no longer knows is no session", async () => {
    cookieJar.set(SESSION_COOKIE, "revoked");
    fakeCoreApi(() => Response.json({ detail: "not_authenticated" }, { status: 401 }));

    expect(await getSession()).toBeNull();
  });

  it("AC7: a private page without a live session goes to /login", async () => {
    cookieJar.set(SESSION_COOKIE, "revoked");
    fakeCoreApi(() => Response.json({ detail: "not_authenticated" }, { status: 401 }));

    await expect(requireSession()).rejects.toThrow("redirect:/login");
  });

  it("AC2: an unverified account goes to /check-email", async () => {
    cookieJar.set(SESSION_COOKIE, "tok");
    fakeCoreApi(() => Response.json({ ...ME, email_verified: false }));

    await expect(requireVerifiedSession()).rejects.toThrow("redirect:/check-email");
  });

  it("a verified account gets its user", async () => {
    cookieJar.set(SESSION_COOKIE, "tok");
    fakeCoreApi(() => Response.json(ME));

    expect(await requireVerifiedSession()).toEqual(ME);
  });

  it("a core-api failure is an error, not a sign-out", async () => {
    cookieJar.set(SESSION_COOKIE, "tok");
    fakeCoreApi(() => new Response(null, { status: 503 }));

    await expect(getSession()).rejects.toThrow();
  });
});
