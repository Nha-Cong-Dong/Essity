// Risk register R22: a success that is not JSON is a failure, never an empty success (it sent
// sign-up to "/undefined"). Web's own routes always answer JSON (review plan P7): a body that is
// not means something in between broke.
import { afterEach, describe, expect, it, vi } from "vitest";

import { postJson } from "@/lib/auth-errors";

afterEach(() => vi.unstubAllGlobals());

function reply(response: Response) {
  vi.stubGlobal("fetch", vi.fn(async () => response));
}

describe("postJson (R22)", () => {
  // Red when: response.json().catch(() => ({})) turns an HTML or empty 2xx into data = {}.
  it.each([
    ["an HTML page", new Response("<html>proxy error</html>", { status: 200 })],
    ["an empty body", new Response(null, { status: 201 })],
    ["JSON that is not an object", new Response("42", { status: 200 })],
    ["a JSON array", Response.json([])],
  ])("a 2xx with %s is unavailable, with no data", async (_name, response) => {
    reply(response);
    const result = await postJson("/api/auth/register", {});
    expect(result.data).toBeUndefined();
    expect(result.error).toBe("unavailable");
  });

  it("a JSON 2xx is data", async () => {
    reply(Response.json({ next: "/check-email" }));
    expect((await postJson("/api/auth/register", {})).data).toEqual({ next: "/check-email" });
  });

  it("an error that is not JSON is still unavailable", async () => {
    reply(new Response("bad gateway", { status: 502 }));
    expect((await postJson("/api/auth/register", {})).error).toBe("unavailable");
  });
});
