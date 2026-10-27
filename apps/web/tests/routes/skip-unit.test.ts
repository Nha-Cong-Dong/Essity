// T2.24 (US-04 AC5): the routes behind "Không cần ôn phần này" and "Hoàn tác".
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DELETE as unskip, POST as skip } from "@/app/api/units/[id]/skip/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const TOKEN = "session-token-marker-skip";
const SIGNED_IN = { cookies: { [SESSION_COOKIE]: TOKEN } };
const ID = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const SESSION = "5a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d";
const params = (id = ID) => ({ params: Promise.resolve({ id }) });
const refusal = (status: number, detail: string) => Response.json({ detail }, { status });

describe("skip routes (T2.24)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  // Red when: the session is not passed on, or core-api's answer (the next question) is lost.
  it("POST passes the session on and answers the next question", async () => {
    const calls = fakeCoreApi(() => Response.json({ session_id: SESSION, next: null }));
    const response = await skip(
      browserPost(`/api/units/${ID}/skip`, { review_session_id: SESSION }, SIGNED_IN),
      params(),
    );
    expect(calls[0].path).toBe(`/v1/units/${ID}/skip`);
    expect(calls[0].body).toEqual({ review_session_id: SESSION });
    expect(calls[0].headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ session_id: SESSION, next: null });
  });

  it("POST refuses a body with another field or a bad session id, without a call", async () => {
    const calls = fakeCoreApi(() => Response.json({}));
    const extra = await skip(
      browserPost(`/api/units/${ID}/skip`, { review_session_id: SESSION, x: 1 }, SIGNED_IN),
      params(),
    );
    const bad = await skip(
      browserPost(`/api/units/${ID}/skip`, { review_session_id: "../x" }, SIGNED_IN),
      params(),
    );
    expect(extra.status).toBe(400);
    expect(bad.status).toBe(400);
    expect(calls).toHaveLength(0);
  });

  it("a non-UUID unit id is 404 and signed out is 401, without a call", async () => {
    const calls = fakeCoreApi(() => Response.json({}));
    const bad = await skip(browserPost(`/api/units/x/skip`, { review_session_id: SESSION }, SIGNED_IN), params("../x"));
    const out = await skip(browserPost(`/api/units/${ID}/skip`, {}, { cookies: {} }), params());
    expect(bad.status).toBe(404);
    expect(out.status).toBe(401);
    expect(calls).toHaveLength(0);
  });

  it.each([
    [404, "unit_not_found"],
    [404, "session_not_found"],
  ])("core-api %i %s goes through with its code", async (status, detail) => {
    fakeCoreApi(() => refusal(status, detail));
    const response = await skip(browserPost(`/api/units/${ID}/skip`, {}, SIGNED_IN), params());
    expect(response.status).toBe(status);
    expect(await response.json()).toEqual({ error: detail });
  });

  // Red when: the undo drops the session id from the query, so the lock order and 404 check are lost.
  it("DELETE undoes the skip for the session and answers 204", async () => {
    const calls = fakeCoreApi(() => new Response(null, { status: 204 }));
    const response = await unskip(
      browserPost(`/api/units/${ID}/skip?review_session_id=${SESSION}`, undefined, { ...SIGNED_IN, method: "DELETE" }),
      params(),
    );
    expect(calls[0].method).toBe("DELETE");
    expect(calls[0].path).toBe(`/v1/units/${ID}/skip`);
    expect(calls[0].search).toBe(`?review_session_id=${SESSION}`);
    expect(response.status).toBe(204);
  });
});
