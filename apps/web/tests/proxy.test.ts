import { NextRequest } from "next/server";
import { describe, expect, it, vi } from "vitest";

import { SESSION_COOKIE } from "@/lib/session";
import { designPreviewAllowed, isDesignPreview } from "@/lib/design-preview";
import { PUBLIC_PAGES, config, proxy } from "@/proxy";

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

  it("review cdbaa25 #2: runs on page paths with a dot, skips only static files and API routes", () => {
    const [matcher] = config.matcher;
    const runs = (path: string) => new RegExp(`^${matcher}$`).test(path);
    expect(runs("/subjects/de-thi.v2")).toBe(true);
    expect(runs("/today")).toBe(true);
    expect(runs("/")).toBe(true);
    expect(runs("/_next/static/chunks/app.js")).toBe(false);
    expect(runs("/api/auth/login")).toBe(false);
    expect(runs("/favicon.ico")).toBe(false);
    expect(runs("/fonts/x.woff2")).toBe(false);
  });
});

// Plan V11, V14: /design-preview calls core-api on every request (ServiceChain), so outside
// development it is a 404 unless WEB_DESIGN_PREVIEW is exactly "1", whatever the cookie.
describe("/design-preview gate", () => {
  const status = (path: string, cookie?: string) => visit(path, { cookie }).status;

  it("is a 404 in production without the flag, with or without a cookie", () => {
    vi.stubEnv("NODE_ENV", "production");
    expect(status("/design-preview")).toBe(404);
    expect(status("/design-preview", "tok")).toBe(404);
    expect(status("/design-preview?_rsc=1", "tok")).toBe(404);
    expect(status("/design-preview/", "tok")).toBe(404);
  });

  it.each(["true", "0", "yes", " 1", ""])("a flag other than exactly 1 (%j) keeps it closed", (flag) => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_DESIGN_PREVIEW", flag);
    expect(status("/design-preview")).toBe(404);
  });

  it("opens in production with WEB_DESIGN_PREVIEW=1, and in development, without a cookie", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_DESIGN_PREVIEW", "1");
    expect(status("/design-preview")).toBe(200);
    vi.stubEnv("WEB_DESIGN_PREVIEW", "");
    vi.stubEnv("NODE_ENV", "development");
    expect(status("/design-preview")).toBe(200);
  });

  it("is closed when NODE_ENV is missing or test", () => {
    expect(designPreviewAllowed({})).toBe(false);
    expect(designPreviewAllowed({ NODE_ENV: "test" })).toBe(false);
    expect(designPreviewAllowed({ NODE_ENV: "test", WEB_DESIGN_PREVIEW: "1" })).toBe(true);
  });

  it("is not a public page any more", () => {
    expect([...PUBLIC_PAGES]).not.toContain("/design-preview");
  });
});

describe("/design-preview gate against encoded paths (review of 60bb47b)", () => {
  it.each(["/design%2Dpreview", "/design%2dpreview", "//design-preview", "/design-preview%2F", "/%64esign-preview"])(
    "%s is closed in production, even with a cookie",
    (path) => {
      vi.stubEnv("NODE_ENV", "production");
      expect(visit(path, { cookie: "tok" }).status).toBe(404);
    },
  );

  it("a path that cannot be decoded fails closed", () => {
    expect(isDesignPreview("/design-preview%E0%A4%A")).toBe(true);
  });
});

describe("/design-preview second lock in the page (review of 60bb47b)", () => {
  it("renders ServiceChain only behind a check made after connection()", async () => {
    const { readFileSync } = await import("node:fs");
    const page = readFileSync(new URL("../app/design-preview/page.tsx", import.meta.url), "utf-8");
    expect(page.match(/<ServiceChain \/>/g)).toHaveLength(1);
    expect(page).toMatch(
      /await connection\(\);[^\n]*\n\s*if \(!designPreviewAllowed\(process\.env\)\) notFound\(\);\s*\n\s*return <ServiceChain \/>/,
    );
  });
});
