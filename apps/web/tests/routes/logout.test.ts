import { describe, expect, it, vi } from "vitest";

import * as logoutRoute from "@/app/api/auth/logout/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, setCookies } from "../helpers";

const { POST } = logoutRoute;

describe("POST /api/auth/logout (T1.12)", () => {
  it("revokes the session in core-api and clears the cookie", async () => {
    const calls = fakeCoreApi(() => new Response(null, { status: 204 }));

    const response = await POST(
      browserPost("/api/auth/logout", undefined, { cookies: { [SESSION_COOKIE]: "tok" } }),
    );

    expect(calls.map((c) => [c.method, c.path])).toEqual([["POST", "/v1/auth/logout"]]);
    expect(calls[0].headers.get("authorization")).toBe("Bearer tok");
    expect(await response.json()).toEqual({ next: "/login" });
    const cookie = setCookies(response).get(SESSION_COOKIE) ?? "";
    expect(cookie).toMatch(/Max-Age=0/i);
    // A __Host- cookie is only replaced by one with the same attributes.
    expect(cookie).toMatch(/; Secure/i);
    expect(cookie).toMatch(/; Path=\/(;|$)/);
  });

  it("AC7, ADR-0020: clears the cookie even when core-api fails", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    fakeCoreApi(() => {
      throw new TypeError("fetch failed");
    });

    const response = await POST(
      browserPost("/api/auth/logout", undefined, { cookies: { [SESSION_COOKIE]: "tok" } }),
    );

    expect(response.status).toBe(200);
    expect(setCookies(response).get(SESSION_COOKIE)).toMatch(/Max-Age=0/i);
  });

  it("does not call core-api without a session cookie", async () => {
    const calls = fakeCoreApi(() => new Response(null, { status: 204 }));

    const response = await POST(browserPost("/api/auth/logout"));

    expect(calls).toHaveLength(0);
    expect(response.status).toBe(200);
  });

  it("review plan #2: only POST, so an <img> on another site cannot sign anyone out", () => {
    expect(Object.keys(logoutRoute).filter((name) => name !== "POST")).toEqual([]);
  });

  it("ADR-0014: a POST from another site keeps the session", async () => {
    const calls = fakeCoreApi(() => new Response(null, { status: 204 }));

    const response = await POST(
      browserPost("/api/auth/logout", undefined, {
        origin: "https://evil.example",
        cookies: { [SESSION_COOKIE]: "tok" },
      }),
    );

    expect(response.status).toBe(403);
    expect(calls).toHaveLength(0);
    expect(setCookies(response).has(SESSION_COOKIE)).toBe(false);
  });
});
