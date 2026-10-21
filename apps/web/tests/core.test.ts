import { describe, expect, it, vi } from "vitest";

import { coreFetch } from "@/lib/core";

function stubFetch() {
  const fetchMock = vi.fn(async (_url: URL, _init: RequestInit) => new Response("{}"));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("coreFetch", () => {
  it("calls core-api without caching and with a timeout", async () => {
    const fetchMock = stubFetch();

    await coreFetch("/v1/ping");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url.pathname).toBe("/v1/ping");
    expect(init.cache).toBe("no-store");
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it("W3: a caller cannot turn caching back on (review 604a7ad #1)", async () => {
    const fetchMock = stubFetch();

    await coreFetch("/v1/me", { cache: "force-cache", next: { revalidate: 60 } } as RequestInit);

    const [, init] = fetchMock.mock.calls[0];
    expect(init.cache).toBe("no-store");
    expect((init as { next?: unknown }).next).toBeUndefined();
  });

  it.each(["https://evil.example/x", "//evil.example/x", "v1/me", ""])(
    "refuses %j, which could send credentials elsewhere (review 604a7ad #2)",
    async (path) => {
      const fetchMock = stubFetch();
      await expect(coreFetch(path)).rejects.toThrow();
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );
});
