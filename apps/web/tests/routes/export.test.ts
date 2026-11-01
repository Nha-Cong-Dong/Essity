// T9.5 (US-10 AC8): GET /api/export passes the signed-in user's CSV on and nothing else.
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "@/app/api/export/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const TOKEN = "session-token-marker-export";
const get = (cookies: Record<string, string> = { [SESSION_COOKIE]: TOKEN }) =>
  browserPost("/api/export", undefined, { method: "GET", cookies });

describe("GET /api/export", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  // Red when: the CSV is not a download, or core-api is asked without the user's token.
  it("streams core-api's CSV as a download with the session as bearer", async () => {
    const calls = fakeCoreApi(() => new Response("subject,day\nMạng,2026-10-30\n", { headers: { "content-type": "text/csv" } }));
    const response = await GET(get());
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("text/csv");
    expect(response.headers.get("content-disposition")).toContain("attachment");
    expect(await response.text()).toContain("Mạng");
    expect(calls).toHaveLength(1);
    expect(calls[0].path).toBe("/v1/export.csv");
    expect(calls[0].headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
  });

  // Red when: a request without a session still reaches core-api.
  it("answers 401 without a session and does not call core-api", async () => {
    const calls = fakeCoreApi(() => new Response("x"));
    expect((await GET(get({}))).status).toBe(401);
    expect(calls).toHaveLength(0);
  });

  // Red when: core-api's error body leaks into the download, or 401 becomes a 503.
  it("maps 401 to signed_out and any other failure to 503", async () => {
    fakeCoreApi(() => new Response("nope", { status: 401 }));
    expect((await GET(get())).status).toBe(401);
    fakeCoreApi(() => new Response("secret detail", { status: 500 }));
    const failed = await GET(get());
    expect(failed.status).toBe(503);
    expect(await failed.text()).not.toContain("secret");
  });

  it("answers 503 when core-api is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("down"); }));
    expect((await GET(get())).status).toBe(503);
  });
});
