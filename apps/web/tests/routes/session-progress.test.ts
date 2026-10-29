// T4.18 (US-02 AC11): the route that passes core-api's processing state on.
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET as progress } from "@/app/api/sessions/[id]/progress/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const TOKEN = "session-token-marker-progress";
const SIGNED_IN = { cookies: { [SESSION_COOKIE]: TOKEN } };
const ID = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const params = (id = ID) => ({ params: Promise.resolve({ id }) });
const get = (options: Parameters<typeof browserPost>[2] = SIGNED_IN) =>
  browserPost(`/api/sessions/${ID}/progress`, undefined, { ...options, method: "GET" });
const STATE = { session_id: ID, state: "processing", step: "anchoring", percent: 60, reason: null };

describe("session progress route (T4.18)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it("asks core-api as the signed-in user and answers its state", async () => {
    const calls = fakeCoreApi(() => Response.json(STATE));
    const response = await progress(get(), params());
    expect(calls[0].path).toBe(`/v1/sessions/${ID}/progress`);
    expect(calls[0].headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(STATE);
  });

  it("makes no call without a session or with an id that is not one", async () => {
    const calls = fakeCoreApi(() => Response.json(STATE));
    const out = await progress(get({ cookies: {} }), params());
    const bad = await progress(get(), params("../x"));
    expect([out.status, bad.status]).toEqual([401, 404]);
    expect(calls).toHaveLength(0);
  });

  it("answers 404 session_not_found when core-api does, and unavailable when it fails", async () => {
    fakeCoreApi(() => Response.json({ detail: "session_not_found" }, { status: 404 }));
    const missing = await progress(get(), params());
    expect(missing.status).toBe(404);
    expect(await missing.json()).toEqual({ error: "session_not_found" });
    fakeCoreApi(() => new Response("boom", { status: 500 }));
    expect((await progress(get(), params())).status).toBe(503);
  });
});
