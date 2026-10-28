// T4.9: the toc route.
import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET as toc } from "@/app/api/documents/[id]/toc/route";
import { SESSION_COOKIE } from "@/lib/session";

import { fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const TOKEN = "session-token-marker-toc";
const ID = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const params = (id = ID) => ({ params: Promise.resolve({ id }) });
const refusal = (status: number, detail: string) => Response.json({ detail }, { status });

const get = (signedIn = true) =>
  new NextRequest(`http://localhost/api/documents/${ID}/toc`, {
    headers: signedIn ? { cookie: `${SESSION_COOKIE}=${TOKEN}` } : {},
  });

describe("toc route (T4.9)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it("passes the toc on with the session", async () => {
    const out = { document_id: ID, toc: { entries: [] } };
    const calls = fakeCoreApi(() => Response.json(out));
    const response = await toc(get(), params());
    expect(calls[0].path).toBe(`/v1/documents/${ID}/toc`);
    expect(calls[0].headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(await response.json()).toEqual(out);
  });

  it.each([
    [409, "not_indexed"],
    [502, "toc_invalid"],
    [404, "document_not_found"],
  ])("answers core-api's %s %s by its code", async (status, code) => {
    fakeCoreApi(() => refusal(status, code));
    const response = await toc(get(), params());
    expect(response.status).toBe(status);
    expect(await response.json()).toMatchObject({ error: code });
  });

  it("refuses a bad id or no session without a call", async () => {
    const calls = fakeCoreApi(() => Response.json({}));
    const bad = await toc(get(), params("../x"));
    const out = await toc(get(false), params());
    expect([bad.status, out.status]).toEqual([404, 401]);
    expect(calls).toHaveLength(0);
  });
});
