import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { SESSION_COOKIE } from "@/lib/session";
import { proxy } from "@/proxy";

import { ORIGIN } from "./helpers";

function visit(path: string, { cookie }: { cookie?: string } = {}) {
  return proxy(
    new NextRequest(`${ORIGIN}${path}`, {
      headers: cookie ? { cookie: `${SESSION_COOKIE}=${cookie}` } : {},
    }),
  );
}

function redirectedTo(response: Response): string | null {
  const location = response.headers.get("location");
  return location === null ? null : new URL(location).pathname + new URL(location).search;
}

describe("proxy (T1.12, W3: an optimistic cookie check only)", () => {
  it("AC7: sends a private page to /login without a session cookie", () => {
    expect(redirectedTo(visit("/today"))).toBe("/login");
    expect(redirectedTo(visit("/"))).toBe("/login");
    expect(redirectedTo(visit("/subjects/42"))).toBe("/login");
  });

  it("F7: never carries the page along (no ?next=, so no open redirect)", () => {
    expect(redirectedTo(visit("/today?next=https://evil.example"))).toBe("/login");
  });

  it("lets a private page through with a cookie (the page checks it with core-api)", () => {
    expect(redirectedTo(visit("/today", { cookie: "tok" }))).toBeNull();
  });

  it.each([
    "/login",
    "/register",
    "/check-email",
    "/verify-email",
    "/forgot-password",
    "/reset-password",
    "/design-preview",
  ])("F7: %s is public", (path) => {
    expect(redirectedTo(visit(path))).toBeNull();
  });

  it("W3: lets /login through even with a cookie, so a dead cookie cannot loop", () => {
    expect(redirectedTo(visit("/login", { cookie: "revoked" }))).toBeNull();
  });

  it("does not treat a look-alike path as public", () => {
    expect(redirectedTo(visit("/login-help"))).toBe("/login");
    expect(redirectedTo(visit("/registered"))).toBe("/login");
  });
});
