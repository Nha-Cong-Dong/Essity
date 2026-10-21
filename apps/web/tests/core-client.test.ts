import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { coreClient, coreClientFor } from "@/lib/core-client";

const SERVICE_TOKEN = "web-token-for-tests-only-0123456789";

function stubFetch() {
  const fetchMock = vi.fn<(url: URL, init: RequestInit) => Promise<Response>>(async () =>
    Response.json({ id: "u1", email: "a@example.com", email_verified: true }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function sent(fetchMock: ReturnType<typeof stubFetch>) {
  const [url, init] = fetchMock.mock.calls[0];
  return { url, init, headers: new Headers(init.headers) };
}

describe("coreClient (BFF → core-api)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it("sends the session token, the service token and the user's IP", async () => {
    const fetchMock = stubFetch();

    await coreClient({ token: "session-token", clientIp: "203.0.113.7" }).GET("/v1/me");

    const { url, headers } = sent(fetchMock);
    expect(url.pathname).toBe("/v1/me");
    expect(headers.get("authorization")).toBe("Bearer session-token");
    expect(headers.get("x-service-token")).toBe(SERVICE_TOKEN);
    expect(headers.get("x-client-ip")).toBe("203.0.113.7");
  });

  it("W3: goes through coreFetch, so it is never cached and has a timeout (review 57e3969 #1)", async () => {
    const fetchMock = stubFetch();

    await coreClient({ token: "session-token" }).GET("/v1/me");

    const { init } = sent(fetchMock);
    expect(init.cache).toBe("no-store");
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it("sends a JSON body", async () => {
    const fetchMock = stubFetch();

    await coreClient().POST("/v1/auth/login", {
      body: { email: "a@example.com", password: "correct horse" },
    });

    const { init, headers } = sent(fetchMock);
    expect(init.method).toBe("POST");
    expect(headers.get("content-type")).toBe("application/json");
    expect(JSON.parse(new TextDecoder().decode(init.body as ArrayBuffer))).toEqual({
      email: "a@example.com",
      password: "correct horse",
    });
  });

  it("sends neither Authorization nor X-Client-IP when it has none", async () => {
    const fetchMock = stubFetch();

    await coreClient().GET("/v1/me");

    const { headers } = sent(fetchMock);
    expect(headers.has("authorization")).toBe(false);
    expect(headers.has("x-client-ip")).toBe(false);
  });

  it("AC6: never sends an IP without the service token (core-api would not trust it)", async () => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", undefined);
    const fetchMock = stubFetch();

    await coreClient({ clientIp: "203.0.113.7" }).GET("/v1/me");

    expect(sent(fetchMock).headers.has("x-client-ip")).toBe(false);
  });

  it("AC6: coreClientFor takes the IP from X-Forwarded-For only behind a trusted proxy", async () => {
    vi.stubEnv("WEB_TRUSTED_PROXY_HOPS", "1");
    const fetchMock = stubFetch();
    const request = new NextRequest("http://localhost:3000/api/auth/login", {
      method: "POST",
      headers: { "x-forwarded-for": "1.1.1.1, 203.0.113.7" },
    });

    await coreClientFor(request).GET("/v1/me");

    expect(sent(fetchMock).headers.get("x-client-ip")).toBe("203.0.113.7");
  });

  it.each(["0", "1"])(
    "AC6: never forwards an X-Client-IP the browser sent itself (hops = %s, review 987ad20 #1)",
    async (hops) => {
      vi.stubEnv("WEB_TRUSTED_PROXY_HOPS", hops);
      const fetchMock = stubFetch();
      const request = new NextRequest("http://localhost:3000/api/auth/login", {
        method: "POST",
        headers: { "x-client-ip": "9.9.9.9", "x-forwarded-for": "203.0.113.7" },
      });

      await coreClientFor(request).GET("/v1/me");

      expect(sent(fetchMock).headers.get("x-client-ip")).toBe(hops === "0" ? null : "203.0.113.7");
    },
  );
});
