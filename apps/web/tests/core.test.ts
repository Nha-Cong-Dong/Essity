import { describe, expect, it, vi } from "vitest";

import { coreFetch } from "@/lib/core";

describe("coreFetch", () => {
  it("calls core-api without caching and with a timeout", async () => {
    const fetchMock = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);

    await coreFetch("/v1/ping");

    const [url, init] = fetchMock.mock.calls[0] as unknown as [URL, RequestInit];
    expect(url.pathname).toBe("/v1/ping");
    expect(init.cache).toBe("no-store");
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });
});
