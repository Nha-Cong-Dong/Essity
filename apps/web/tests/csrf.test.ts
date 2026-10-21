import { NextRequest } from "next/server";
import { describe, expect, it, vi } from "vitest";

import { isAllowedOrigin, withOrigin } from "@/lib/csrf";

const ORIGIN = "http://localhost:3000";

function post(headers: Record<string, string> = {}): NextRequest {
  return new NextRequest(`${ORIGIN}/api/auth/login`, { method: "POST", headers });
}

describe("isAllowedOrigin (ADR-0014 CSRF, W5)", () => {
  it("accepts our own origin", () => {
    expect(isAllowedOrigin(post({ origin: ORIGIN }), ORIGIN)).toBe(true);
  });

  it.each([
    ["a foreign origin", { origin: "https://evil.example" }],
    ["a look-alike origin", { origin: "http://localhost:3000.evil.example" }],
    ["another port", { origin: "http://localhost:3001" }],
    ["an opaque origin", { origin: "null" }],
    ["no origin", {}],
  ])("refuses %s", (_name, headers) => {
    expect(isAllowedOrigin(post(headers), ORIGIN)).toBe(false);
  });
});

describe("withOrigin", () => {
  it("returns 403 without calling the handler when the origin is wrong", async () => {
    const handler = vi.fn(async () => new Response("ok"));
    const response = await withOrigin(handler)(post({ origin: "https://evil.example" }));
    expect(response.status).toBe(403);
    expect(handler).not.toHaveBeenCalled();
  });

  it("calls the handler for our own origin", async () => {
    const handler = vi.fn(async () => new Response("ok"));
    const response = await withOrigin(handler)(post({ origin: ORIGIN }));
    expect(response.status).toBe(200);
    expect(handler).toHaveBeenCalledOnce();
  });

  it("returns 500 without calling the handler when the configuration is incomplete", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_ORIGIN", ORIGIN);
    vi.spyOn(console, "error").mockImplementation(() => {});
    const handler = vi.fn(async () => new Response("ok"));
    const response = await withOrigin(handler)(post({ origin: ORIGIN }));
    expect(response.status).toBe(500);
    expect(handler).not.toHaveBeenCalled();
  });
});
