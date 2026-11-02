// T4.13a: the routes behind "Ghi buổi học" (US-02 AC1, AC4, AC7).
import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as confirm } from "@/app/api/sessions/[id]/confirm/route";
import { POST as noteUrl } from "@/app/api/sessions/[id]/notes/upload-url/route";
import { POST as describeSession } from "@/app/api/subjects/[id]/sessions/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const TOKEN = "session-token-marker-log";
const SIGNED_IN = { cookies: { [SESSION_COOKIE]: TOKEN } };
const ID = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const DOC = "5a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d";
const params = (id = ID) => ({ params: Promise.resolve({ id }) });
const refusal = (status: number, detail: string) => Response.json({ detail }, { status });
const SHA = "ab".repeat(32);
const NOTE = { sha256: SHA, mime: "image/jpeg", size_bytes: 1234 };
const RANGE = { document_id: DOC, start_page: 43, end_page: 58, depth: "deep" };

describe("session routes (T4.13a)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  // Red when: the sentence or the session is not passed on, or the card is lost.
  it("describe passes the sentence on and answers the card with core-api's 201", async () => {
    const card = { session_id: ID, card: "manual", documents: [], ranges: [] };
    const calls = fakeCoreApi(() => Response.json(card, { status: 201 }));
    const response = await describeSession(
      browserPost(`/api/subjects/${ID}/sessions`, { description: "học tiếp" }, SIGNED_IN),
      params(),
    );
    expect(calls[0].path).toBe(`/v1/subjects/${ID}/sessions`);
    expect(calls[0].body).toEqual({ description: "học tiếp" });
    expect(calls[0].headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(response.status).toBe(201);
    expect(await response.json()).toEqual(card);
  });

  it("describe refuses another field, a bad id or no session, without a call", async () => {
    const calls = fakeCoreApi(() => Response.json({}));
    const body = { description: "x" };
    const extra = await describeSession(browserPost("/api/s", { ...body, a: 1 }, SIGNED_IN), params());
    const bad = await describeSession(browserPost("/api/s", body, SIGNED_IN), params("../x"));
    const out = await describeSession(browserPost("/api/s", body, { cookies: {} }), params());
    expect([extra.status, bad.status, out.status]).toEqual([400, 404, 401]);
    expect(calls).toHaveLength(0);
  });

  it.each([
    [404, "subject_not_found", 404],
    [422, "anything", 422],
    [500, "boom", 503],
  ])("describe turns core-api's %i %s into %i", async (status, detail, expected) => {
    fakeCoreApi(() => refusal(status, detail));
    const response = await describeSession(
      browserPost("/api/s", { description: "x" }, SIGNED_IN),
      params(),
    );
    expect(response.status).toBe(expected);
  });

  it("describe passes core-api's 429 on with its Retry-After", async () => {
    fakeCoreApi(() => new Response("{}", { status: 429, headers: { "retry-after": "60" } }));
    const response = await describeSession(
      browserPost("/api/s", { description: "x" }, SIGNED_IN),
      params(),
    );
    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("60");
  });

  it("confirm passes the ranges and day on, rebuilt, and answers the saved session", async () => {
    const saved = { session_id: ID, status: "confirmed" };
    const calls = fakeCoreApi(() => Response.json(saved));
    const response = await confirm(
      browserPost("/api/c", { ranges: [{ ...RANGE, start_label: "43" }], studied_on: "2026-10-28" }, SIGNED_IN),
      params(),
    );
    expect(calls[0].path).toBe(`/v1/sessions/${ID}/confirm`);
    expect(calls[0].body).toEqual({ ranges: [{ ...RANGE, start_label: "43" }], studied_on: "2026-10-28", notes: [] });
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(saved);
  });

  it.each([
    ["a note with another key", { ranges: [], notes: [{ ...NOTE, object_key: "users/x" }] }],
    ["a note with a bad hash", { ranges: [], notes: [{ ...NOTE, sha256: "AB".repeat(32) }] }],
    ["a note of a type not allowed", { ranges: [], notes: [{ ...NOTE, mime: "image/gif" }] }],
    ["a note of no size", { ranges: [], notes: [{ ...NOTE, size_bytes: 0 }] }],
    ["notes that are not a list", { ranges: [], notes: "x" }],
    ["21 notes", { ranges: [], notes: Array(21).fill(NOTE) }],
    ["a bad depth", { ranges: [{ ...RANGE, depth: "x" }] }],
    ["a non-integer page", { ranges: [{ ...RANGE, start_page: 1.5 }] }],
    ["a document that is not a UUID", { ranges: [{ ...RANGE, document_id: "../x" }] }],
    ["no ranges", {}],
    ["seven ranges", { ranges: Array(7).fill(RANGE) }],
    ["a day that is not text", { ranges: [], studied_on: 5 }],
  ])("confirm refuses %s without a call", async (_name, body) => {
    const calls = fakeCoreApi(() => Response.json({}));
    const response = await confirm(browserPost("/api/c", body, SIGNED_IN), params());
    expect(response.status).toBe(400);
    expect(calls).toHaveLength(0);
  });

  it.each([
    [422, "bad_range"],
    [422, "bad_date"],
    [404, "document_not_found"],
    [409, "not_indexed"],
    [404, "session_not_found"],
  ])("confirm passes core-api's %i %s on as its code", async (status, detail) => {
    fakeCoreApi(() => refusal(status, detail));
    const response = await confirm(browserPost("/api/c", { ranges: [RANGE] }, SIGNED_IN), params());
    expect(response.status).toBe(status);
    expect(await response.json()).toEqual({ error: detail });
  });

  // Red when: the notes the learner confirms are dropped (as in T4.13a) or passed on unchecked.
  it("confirm passes the notes on, rebuilt field by field", async () => {
    const calls = fakeCoreApi(() => Response.json({ session_id: ID }));
    const response = await confirm(
      browserPost("/api/c", { ranges: [], notes: [NOTE] }, SIGNED_IN),
      params(),
    );
    expect(response.status).toBe(200);
    expect(calls[0].body).toEqual({ ranges: [], notes: [NOTE] });
  });

  it.each([
    [409, "upload_incomplete"],
    [422, "content_mismatch"],
    [422, "size_mismatch"],
    [422, "bad_note"],
  ])("confirm passes core-api's %i %s on as its code", async (status, detail) => {
    fakeCoreApi(() => refusal(status, detail));
    const response = await confirm(browserPost("/api/c", { ranges: [], notes: [NOTE] }, SIGNED_IN), params());
    expect(response.status).toBe(status);
    expect(await response.json()).toEqual({ error: detail });
  });
});

describe("note upload URL route (T4.13b)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  const signed = {
    url: "https://files.example/x",
    method: "PUT",
    headers: { "Content-Type": "image/jpeg" },
    expires_at: "2026-10-29T10:00:00Z",
  };

  it("asks core-api for the file's URL and answers it", async () => {
    const calls = fakeCoreApi(() => Response.json(signed, { status: 201 }));
    const response = await noteUrl(browserPost("/api/n", NOTE, SIGNED_IN), params());
    expect(calls[0].path).toBe(`/v1/sessions/${ID}/notes/upload-url`);
    expect(calls[0].body).toEqual(NOTE);
    expect(calls[0].headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(response.status).toBe(201);
    expect(await response.json()).toEqual(signed);
  });

  // US-02 AC13 (T7.12c). Red when: Word or PowerPoint of a v2 submission is refused before core-api.
  it("passes Word and PowerPoint on for a submission's file", async () => {
    const calls = fakeCoreApi(() => Response.json(signed, { status: 201 }));
    const docx = { ...NOTE, mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" };
    expect((await noteUrl(browserPost("/api/n", docx, SIGNED_IN), params())).status).toBe(201);
    expect(calls[0].body).toEqual(docx);
  });

  it.each([
    ["another field", { ...NOTE, object_key: "k" }],
    ["a type not allowed", { ...NOTE, mime: "text/html" }],
    ["a bad hash", { ...NOTE, sha256: "zz" }],
    ["a size that is not an integer", { ...NOTE, size_bytes: 1.5 }],
    ["no size", { sha256: SHA, mime: "image/png" }],
  ])("refuses %s without a call", async (_name, body) => {
    const calls = fakeCoreApi(() => Response.json({}));
    const response = await noteUrl(browserPost("/api/n", body, SIGNED_IN), params());
    expect(response.status).toBe(400);
    expect(calls).toHaveLength(0);
  });

  it("refuses a bad session id or no cookie without a call", async () => {
    const calls = fakeCoreApi(() => Response.json({}));
    const bad = await noteUrl(browserPost("/api/n", NOTE, SIGNED_IN), params("../x"));
    const out = await noteUrl(browserPost("/api/n", NOTE, { cookies: {} }), params());
    expect([bad.status, out.status]).toEqual([404, 401]);
    expect(calls).toHaveLength(0);
  });

  it.each([
    [404, "session_not_found"],
    [409, "session_confirmed"],
    [409, "too_many_notes"],
    [409, "storage_quota_exceeded"],
    [422, "file_too_large"],
    [422, "bad_note"],
  ])("passes core-api's %i %s on as its code", async (status, detail) => {
    fakeCoreApi(() => refusal(status, detail));
    const response = await noteUrl(browserPost("/api/n", NOTE, SIGNED_IN), params());
    expect(response.status).toBe(status);
    expect(await response.json()).toEqual({ error: detail });
  });

  it("passes core-api's 429 on with its Retry-After", async () => {
    fakeCoreApi(() => new Response("{}", { status: 429, headers: { "retry-after": "30" } }));
    const response = await noteUrl(browserPost("/api/n", NOTE, SIGNED_IN), params());
    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("30");
  });
});

describe("web to core-api timeout of the card (T4.13a hand-off, #61)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  // Red when: the sentence's call is cut at the default 5 s (core-api's budget is 4.5 s, so a
  // card at 4.6 s would be thrown away) or has no cutoff at all.
  it("describe waits up to 6000 ms for the card", async () => {
    const timeout = vi.spyOn(AbortSignal, "timeout");
    fakeCoreApi(() => Response.json({ session_id: ID, card: "manual" }, { status: 201 }));
    await describeSession(browserPost("/api/s", { description: "x" }, SIGNED_IN), params());
    expect(timeout).toHaveBeenCalledWith(6000);
    timeout.mockRestore();
  });

  it("describe answers 503 unavailable when the call is aborted", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new DOMException("The operation was aborted", "AbortError");
      }),
    );
    const response = await describeSession(browserPost("/api/s", { description: "x" }, SIGNED_IN), params());
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ error: "unavailable" });
  });
});
