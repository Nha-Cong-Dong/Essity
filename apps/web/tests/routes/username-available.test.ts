import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "@/app/api/auth/username-available/route";

import { fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const ask = (username: string) =>
  GET(new Request(`http://localhost:3000/api/auth/username-available?username=${encodeURIComponent(username)}`));

describe("GET /api/auth/username-available (T1.24)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it("asks core-api about a well-formed name and passes {available, reason} on", async () => {
    const calls = fakeCoreApi(() => Response.json({ available: false, reason: "taken" }));

    const response = await ask("an.nguyen");

    expect(calls[0].path).toBe("/v1/auth/username-availability");
    expect(calls[0].search).toBe("?u=an.nguyen");
    expect(calls[0].headers.get("x-service-token")).toBe(SERVICE_TOKEN);
    expect(await response.json()).toEqual({ available: false, reason: "taken" });
  });

  it("forwards the user's IP in x-client-ip, from X-Forwarded-For behind one proxy hop (AC6)", async () => {
    vi.stubEnv("WEB_TRUSTED_PROXY_HOPS", "1");
    const calls = fakeCoreApi(() => Response.json({ available: true, reason: null }));

    await GET(
      new Request("http://localhost:3000/api/auth/username-available?username=an.nguyen", {
        headers: { "x-forwarded-for": "203.0.113.7", "x-client-ip": "9.9.9.9" },
      }),
    );

    expect(calls[0].headers.get("x-client-ip")).toBe("203.0.113.7");
  });

  it("never asks core-api about a malformed name", async () => {
    const calls = fakeCoreApi(() => Response.json({ available: true, reason: null }));

    for (const name of ["", "ab", "An.Nguyen", "an nguyen", "1abc", "a..b", "x".repeat(21)]) {
      expect((await ask(name)).status).toBe(400);
    }
    expect(calls).toHaveLength(0);
  });

  it("a 5xx is unavailable, never 'available'", async () => {
    fakeCoreApi(() => new Response("boom", { status: 500 }));
    expect((await ask("an.nguyen")).status).toBe(503);
  });

  it("AC6: passes a 429 on with its Retry-After", async () => {
    fakeCoreApi(() => new Response("{}", { status: 429, headers: { "retry-after": "30" } }));
    const response = await ask("an.nguyen");
    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("30");
  });
});
