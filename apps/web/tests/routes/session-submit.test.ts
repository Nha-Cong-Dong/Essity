// T7.12 / CARDS-V3: the routes behind the study session: the submission and where it stands (US-02 AC2-AC4, AC13).
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET as result } from "@/app/api/sessions/[id]/result/route";
import { POST as submit } from "@/app/api/submissions/route";
import { POST as startDraft } from "@/app/api/subjects/[id]/submission-drafts/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const TOKEN = "session-token-marker-session";
const SIGNED_IN = { cookies: { [SESSION_COOKIE]: TOKEN } };
const ID = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const OTHER = "5a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d";
const params = (id = ID) => ({ params: Promise.resolve({ id }) });
const refusal = (status: number, detail: unknown) => Response.json({ detail }, { status });

describe("session routes (T7.12, CARDS-V3)", () => {
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
    const body = { session_id: ID, description: "học @Giáo trình phần 3.2", mentions: [{ document_id: OTHER, start: 4, end: 14 }] };
    const response = await submit(browserPost("/x", body, SIGNED_IN));
    expect(calls[0].path).toBe("/v1/submissions");
    // T7.19 F1: with no file the sentence is also the note (core-api refuses "nothing_submitted" else).
    expect(calls[0].body).toEqual({ ...body, files: [], text: body.description });
    expect(response.status).toBe(201);
    const bad = [
      { ...body, extra: 1 },
      { ...body, text: "x" },
      { ...body, session_id: "../x" },
      { ...body, description: "x".repeat(2001) },
      { ...body, mentions: [{ document_id: OTHER, start: 1 }] },
    ];
    for (const item of bad) expect((await submit(browserPost("/x", item, SIGNED_IN))).status).toBe(400);
    expect(calls).toHaveLength(1);
  });

  // US-02 AC1, AC13. Red when: the uploaded files are not handed in with the sentence, a file key is
  // passed on unchecked, or more than 20 files go through.
  it("submissions pass the uploaded files on as hash, type and size only", async () => {
    const calls = fakeCoreApi(() => Response.json({ submission_id: OTHER, session_id: ID, status: "queued", mentions: [] }, { status: 201 }));
    const file = { sha256: "ab".repeat(32), mime: "image/png", size_bytes: 12 };
    const docx = { sha256: "cd".repeat(32), mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", size_bytes: 9 };
    const body = { session_id: ID, description: "", mentions: [], files: [file, docx] };
    expect((await submit(browserPost("/x", body, SIGNED_IN))).status).toBe(201);
    expect(calls[0].body).toEqual(body);
    const bad = [
      { ...body, files: [{ ...file, object_key: "k" }] },
      { ...body, files: [{ ...file, mime: "text/html" }] },
      { ...body, files: [{ ...file, sha256: "zz" }] },
      { ...body, files: [{ ...file, size_bytes: 0 }] },
      { ...body, files: Array.from({ length: 21 }, () => file) },
      { ...body, files: "x" },
    ];
    for (const item of bad) expect((await submit(browserPost("/x", item, SIGNED_IN))).status).toBe(400);
    expect(calls).toHaveLength(1);
  });

  // T7.19 F1. Red when: a note with only words is handed over without them as the note, or a blank
  // sentence becomes a note, or a note with files also repeats the sentence as a second file.
  it("submissions make the sentence the note only when there is no file and it is not blank", async () => {
    const calls = fakeCoreApi(() => Response.json({ submission_id: OTHER, session_id: ID, status: "queued", mentions: [] }, { status: 201 }));
    const file = { sha256: "ab".repeat(32), mime: "image/png", size_bytes: 12 };
    const base = { session_id: ID, mentions: [] };
    await submit(browserPost("/x", { ...base, description: "hai dòng ghi chú" }, SIGNED_IN));
    await submit(browserPost("/x", { ...base, description: "   " }, SIGNED_IN));
    await submit(browserPost("/x", { ...base, description: "kèm ảnh", files: [file] }, SIGNED_IN));
    expect(calls[0].body).toMatchObject({ text: "hai dòng ghi chú" });
    expect(calls[1].body).not.toHaveProperty("text");
    expect(calls[2].body).not.toHaveProperty("text");
  });

  // US-02 AC4. Red when: the index of the mention that did not resolve is not passed on, or the
  // text core-api quotes back (`part`) reaches the browser.
  it("submissions turn a mention refusal into its code and index, without the text", async () => {
    fakeCoreApi(() => refusal(422, { code: "scope_not_found", mention: 1, part: "phần 9.9", candidates: [] }));
    const body = { session_id: ID, description: "x", mentions: [] };
    const response = await submit(browserPost("/x", body, SIGNED_IN));
    expect(response.status).toBe(422);
    expect(await response.json()).toEqual({ error: "scope_not_found", mention: 1 });
  });

  // CARDS-V3. Red when: the result is not asked from the vault route, needs no session, or drops the notice.
  it("reads where the session stands from the vault, and needs a session", async () => {
    const out = { session_id: ID, submission_status: "done", title: "TCP", cards: 0, notice: "no_content_found" };
    const calls = fakeCoreApi(() => Response.json(out));
    const response = await result(browserPost("/x", undefined, { ...SIGNED_IN, method: "GET" }), params());
    expect(calls[0].path).toBe(`/v1/vault/sessions/${ID}/result`);
    expect(await response.json()).toEqual(out);
    const signedOut = await result(browserPost("/x", undefined, { method: "GET" }), params());
    expect(signedOut.status).toBe(401);
  });
});

describe("dropping a piece (Q4b)", () => {
  // Red when: the piece id is passed on unchecked, or a 204 becomes "unavailable".
  it("passes the delete on and answers 204", async () => {
    const { DELETE } = await import("@/app/api/sessions/[id]/pieces/[pieceId]/route");
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
    const calls = fakeCoreApi(() => new Response(null, { status: 204 }));
    const request = browserPost("/x", undefined, { ...SIGNED_IN, method: "DELETE" });
    const response = await DELETE(request, { params: Promise.resolve({ id: ID, pieceId: OTHER }) });
    expect(response.status).toBe(204);
    expect(calls[0].path).toBe(`/v1/study-sessions/${ID}/pieces/${OTHER}`);
    expect(calls[0].method).toBe("DELETE");
    const bad = await DELETE(request, { params: Promise.resolve({ id: ID, pieceId: "../x" }) });
    expect(bad.status).toBe(404);
    expect(calls).toHaveLength(1);
  });
});
