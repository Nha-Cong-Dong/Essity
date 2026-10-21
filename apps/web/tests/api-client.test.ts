import { createCoreClient } from "@essity/api-client";
import { describe, expect, it, vi } from "vitest";

describe("@essity/api-client", () => {
  it("calls a typed core-api path", async () => {
    const fetchMock = vi.fn<(request: Request) => Promise<Response>>(async () =>
      Response.json({ status: "ok" }),
    );
    const client = createCoreClient({ baseUrl: "http://core.test", fetch: fetchMock });

    const { data } = await client.GET("/healthz");

    expect(fetchMock.mock.calls[0][0].url).toBe("http://core.test/healthz");
    expect(data).toEqual({ status: "ok" });
  });
});
