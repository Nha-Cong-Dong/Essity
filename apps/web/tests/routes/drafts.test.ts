// T7.12: the routes behind the study session's drafts (US-02 AC2-AC4, AC13; US-02b AC6-AC9).
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DELETE as discard, GET as readCard, PATCH as edit } from "@/app/api/drafts/[id]/route";
import { POST as split } from "@/app/api/drafts/[id]/split/route";
import { POST as undo } from "@/app/api/drafts/[id]/undo/route";
import { GET as list, POST as add } from "@/app/api/sessions/[id]/drafts/route";
import { POST as merge } from "@/app/api/sessions/[id]/drafts/merge/route";
import { POST as save } from "@/app/api/sessions/[id]/drafts/save/route";
import { POST as submit } from "@/app/api/submissions/route";
import { POST as startDraft } from "@/app/api/subjects/[id]/submission-drafts/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const TOKEN = "session-token-marker-drafts";
const SIGNED_IN = { cookies: { [SESSION_COOKIE]: TOKEN } };
const ID = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const OTHER = "5a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d";
const params = (id = ID) => ({ params: Promise.resolve({ id }) });
const refusal = (status: number, detail: unknown) => Response.json({ detail }, { status });

describe("draft routes (T7.12)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  // US-02 AC13. Red when: the empty session is not asked for the subject in the path.
  it("submission-drafts asks core-api for an empty session of the subject", async () => {
    const calls = fakeCoreApi(() => Response.json({ session_id: OTHER }, { status: 201 }));
    const response = await startDraft(browserPost("/x", undefined, SIGNED_IN), params());
    expect(calls[0].path).toBe(`/v1/subjects/${ID}/submission-drafts`);
    expect(response.status).toBe(201);
    expect(await response.json()).toEqual({ session_id: OTHER });
  });

  // US-02 AC2, AC3. Red when: the sentence or a mention is lost, or another key goes on.
  it("submissions pass the sentence and the mentions on, nothing else", async () => {
    const out = { submission_id: OTHER, session_id: ID, status: "queued", mentions: [] };
    const calls = fakeCoreApi(() => Response.json(out, { status: 201 }));
    const body = { session_id: ID, description: "học @Giáo trình mục 3.2", mentions: [{ document_id: OTHER, start: 4, end: 14 }] };
    const response = await submit(browserPost("/x", body, SIGNED_IN));
    expect(calls[0].path).toBe("/v1/submissions");
    expect(calls[0].body).toEqual({ ...body, files: [] });
    expect(response.status).toBe(201);
    const bad = [
      { ...body, extra: 1 },
      { ...body, session_id: "../x" },
      { ...body, description: "x".repeat(2001) },
      { ...body, mentions: [{ document_id: OTHER, start: 1 }] },
    ];
    for (const item of bad) expect((await submit(browserPost("/x", item, SIGNED_IN))).status).toBe(400);
    expect(calls).toHaveLength(1);
  });

  // US-02 AC4. Red when: the index of the mention that did not resolve is not passed on, or the
  // text core-api quotes back (`part`) reaches the browser.
  it("submissions turn a mention refusal into its code and index, without the text", async () => {
    fakeCoreApi(() => refusal(422, { code: "scope_not_found", mention: 1, part: "mục 9.9", candidates: [] }));
    const body = { session_id: ID, description: "x", mentions: [] };
    const response = await submit(browserPost("/x", body, SIGNED_IN));
    expect(response.status).toBe(422);
    expect(await response.json()).toEqual({ error: "scope_not_found", mention: 1 });
  });

  // US-02b AC6. Red when: the list does not need a session, or the status is dropped.
  it("lists the cards with where the submission stands, and needs a session", async () => {
    const out = { drafts: [], submission_status: "pending_ai" };
    const calls = fakeCoreApi(() => Response.json(out));
    const request = browserPost("/x", undefined, { ...SIGNED_IN, method: "GET" });
    const response = await list(request, params());
    expect(calls[0].path).toBe(`/v1/sessions/${ID}/drafts`);
    expect(await response.json()).toEqual(out);
    const signedOut = await list(browserPost("/x", undefined, { method: "GET" }), params());
    expect(signedOut.status).toBe(401);
  });

  // US-02b AC6, AC7. Red when: the version the browser saw is not sent as If-Match, or the
  // 409 loses its code ("thẻ đã đổi ở nơi khác").
  it("edit sends the version as If-Match and names a 409", async () => {
    const calls = fakeCoreApi(() => Response.json({ id: ID }));
    await edit(browserPost("/x", { version: 3, title: "T", content: "C" }, { ...SIGNED_IN, method: "PATCH" }), params());
    expect(calls[0].method).toBe("PATCH");
    expect(calls[0].headers.get("if-match")).toBe("3");
    expect(calls[0].body).toEqual({ title: "T", content: "C" });
    fakeCoreApi(() => refusal(409, { code: "unit_changed_elsewhere", message: "m" }));
    const stale = await edit(browserPost("/x", { version: 1, content: "C" }, { ...SIGNED_IN, method: "PATCH" }), params());
    expect(stale.status).toBe(409);
    expect(await stale.json()).toEqual({ error: "unit_changed_elsewhere" });
  });

  it("edit refuses a body without a version or with another field, without a call", async () => {
    const calls = fakeCoreApi(() => Response.json({}));
    const options = { ...SIGNED_IN, method: "PATCH" };
    const none = await edit(browserPost("/x", { title: "T" }, options), params());
    const extra = await edit(browserPost("/x", { version: 1, status: "canonical" }, options), params());
    const zero = await edit(browserPost("/x", { version: 0, title: "T" }, options), params());
    expect([none.status, extra.status, zero.status]).toEqual([400, 400, 400]);
    expect(calls).toHaveLength(0);
  });

  it("reads, discards and undoes one card", async () => {
    const calls = fakeCoreApi(() => Response.json({ id: ID }));
    await readCard(browserPost("/x", undefined, { ...SIGNED_IN, method: "GET" }), params());
    await discard(browserPost("/x", undefined, { ...SIGNED_IN, method: "DELETE" }), params());
    await undo(browserPost("/x", undefined, SIGNED_IN), params());
    expect(calls.map((call) => `${call.method} ${call.path}`)).toEqual([
      `GET /v1/drafts/${ID}`,
      `DELETE /v1/drafts/${ID}`,
      `POST /v1/drafts/${ID}/undo`,
    ]);
    fakeCoreApi(() => refusal(410, "undo_expired"));
    const late = await undo(browserPost("/x", undefined, SIGNED_IN), params());
    expect([late.status, await late.json()]).toEqual([410, { error: "undo_expired" }]);
  });

  it("add sends the card as a concept; merge and save pass their lists", async () => {
    const calls = fakeCoreApi(() => Response.json({ id: ID, saved: [] }));
    await add(browserPost("/x", { title: "T", content: "C" }, SIGNED_IN), params());
    await merge(browserPost("/x", { unit_ids: [ID, OTHER] }, SIGNED_IN), params());
    await save(browserPost("/x", { units: [{ unit_id: ID, version: 2 }] }, SIGNED_IN), params());
    expect(calls.map((call) => call.body)).toEqual([
      { title: "T", content: "C", kind: "concept" },
      { unit_ids: [ID, OTHER] },
      { units: [{ unit_id: ID, version: 2 }] },
    ]);
    const bad = await merge(browserPost("/x", { unit_ids: [ID] }, SIGNED_IN), params());
    const empty = await save(browserPost("/x", { units: [] }, SIGNED_IN), params());
    expect([bad.status, empty.status]).toEqual([400, 400]);
    expect(calls).toHaveLength(3);
  });

  // US-02b AC8. Red when: split loses If-Match or the parts.
  it("split sends If-Match and the parts", async () => {
    const calls = fakeCoreApi(() => Response.json({ drafts: [], submission_status: null }));
    const parts = [
      { title: "A", content: "a", anchor_ids: [] },
      { title: "B", content: "b", anchor_ids: [OTHER] },
    ];
    await split(browserPost("/x", { version: 2, parts }, SIGNED_IN), params());
    expect(calls[0].headers.get("if-match")).toBe("2");
    expect(calls[0].body).toEqual({ parts });
    const one = await split(browserPost("/x", { version: 2, parts: parts.slice(0, 1) }, SIGNED_IN), params());
    expect(one.status).toBe(400);
  });
});
