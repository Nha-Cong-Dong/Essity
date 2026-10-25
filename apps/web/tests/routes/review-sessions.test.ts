// T2.14: "Bắt đầu" on /today goes through web's POST /api/review-sessions to core-api's
// POST /v1/review-sessions (T2.9). The browser gets the session id, nothing else.
import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "@/app/api/review-sessions/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const TOKEN = "session-token-marker-review";
const SIGNED_IN = { cookies: { [SESSION_COOKIE]: TOKEN } };
const ID = "6b1c2d3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e";
const SUBJECT = "3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b";

describe("POST /api/review-sessions (T2.14)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  // Red when: the session token or the body does not reach core-api, or more than the id comes back.
  it("starts today's session with the user's session and answers its id", async () => {
    const calls = fakeCoreApi(() => Response.json({ id: ID, answered: 0, total: 14 }, { status: 201 }));
    const response = await POST(browserPost("/api/review-sessions", {}, SIGNED_IN));
    expect(calls).toHaveLength(1);
    expect(calls[0].path).toBe("/v1/review-sessions");
    expect(calls[0].body).toEqual({});
    expect(calls[0].headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ id: ID });
  });

  it("the open session (200 from core-api) is answered the same way", async () => {
    fakeCoreApi(() => Response.json({ id: ID, answered: 3, total: 14 }));
    const response = await POST(browserPost("/api/review-sessions", {}, SIGNED_IN));
    expect(await response.json()).toEqual({ id: ID });
  });

  it("US-03 AC7: a subject id is passed on", async () => {
    const calls = fakeCoreApi(() => Response.json({ id: ID, answered: 0, total: 3 }, { status: 201 }));
    await POST(browserPost("/api/review-sessions", { subject_id: SUBJECT }, SIGNED_IN));
    expect(calls[0].body).toEqual({ subject_id: SUBJECT });
  });

  it("nothing_to_review is passed on as its code", async () => {
    fakeCoreApi(() => Response.json({ detail: "nothing_to_review" }, { status: 409 }));
    const response = await POST(browserPost("/api/review-sessions", {}, SIGNED_IN));
    expect(response.status).toBe(409);
    expect(await response.json()).toEqual({ error: "nothing_to_review" });
  });

  it("no session cookie: signed_out, core-api not called", async () => {
    const calls = fakeCoreApi(() => Response.json({}));
    const response = await POST(browserPost("/api/review-sessions", {}));
    expect(response.status).toBe(401);
    expect(calls).toHaveLength(0);
  });

  it.each([[{ subject_id: "not-a-uuid" }], [{ subject_id: SUBJECT, extra: 1 }], [{ subject_id: 7 }]])(
    "a body other than {subject_id?: UUID} is refused before core-api: %j",
    async (body) => {
      const calls = fakeCoreApi(() => Response.json({}));
      const response = await POST(browserPost("/api/review-sessions", body, SIGNED_IN));
      expect(response.status).toBe(400);
      expect(calls).toHaveLength(0);
    },
  );

  it("core-api unreachable: unavailable, not a crash", async () => {
    fakeCoreApi(() => {
      throw new TypeError("fetch failed");
    });
    const response = await POST(browserPost("/api/review-sessions", {}, SIGNED_IN));
    expect(response.status).toBe(503);
  });
});
