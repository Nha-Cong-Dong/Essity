// T4.6: the routes behind the upload step (US-01 AC7).
import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as confirm } from "@/app/api/documents/[id]/confirm/route";
import { POST as ask } from "@/app/api/subjects/[id]/documents/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const TOKEN = "session-token-marker-docs";
const SIGNED_IN = { cookies: { [SESSION_COOKIE]: TOKEN } };
const ID = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const params = (id = ID) => ({ params: Promise.resolve({ id }) });
const ASKED = { filename: "a.pdf", size_bytes: 10, sha256: "a".repeat(64) };
const refusal = (status: number, detail: string) => Response.json({ detail }, { status });

describe("document routes (T4.6)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  // Red when: the body or the session is not passed on, or the signed URL is lost.
  it("ask passes the file's facts on and answers core-api's JSON with its status", async () => {
    const out = { document: { id: ID }, duplicate: false, upload: { url: "https://s/x", headers: {} } };
    const calls = fakeCoreApi(() => Response.json(out, { status: 201 }));
    const response = await ask(browserPost(`/api/subjects/${ID}/documents`, ASKED, SIGNED_IN), params());
    expect(calls[0].path).toBe(`/v1/subjects/${ID}/documents`);
    expect(calls[0].body).toEqual(ASKED);
    expect(calls[0].headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(response.status).toBe(201);
    expect(await response.json()).toEqual(out);
  });

  it("ask refuses another field, a bad id or no session, without a call", async () => {
    const calls = fakeCoreApi(() => Response.json({}));
    const extra = await ask(browserPost(`/api/subjects/${ID}/documents`, { ...ASKED, x: 1 }, SIGNED_IN), params());
    const bad = await ask(browserPost(`/api/subjects/x/documents`, ASKED, SIGNED_IN), params("../x"));
    const out = await ask(browserPost(`/api/subjects/${ID}/documents`, ASKED, { cookies: {} }), params());
    expect([extra.status, bad.status, out.status]).toEqual([400, 404, 401]);
    expect(calls).toHaveLength(0);
  });

  it.each([
    [409, "storage_quota_exceeded"],
    [422, "unsupported_file_type"],
    [422, "file_too_large"],
    [404, "subject_not_found"],
    [503, "storage_full"],
  ])("ask passes core-api's %i %s on as its code", async (status, detail) => {
    fakeCoreApi(() => refusal(status, detail));
    const response = await ask(browserPost(`/api/subjects/${ID}/documents`, ASKED, SIGNED_IN), params());
    expect(response.status).toBe(status);
    expect(await response.json()).toEqual({ error: detail });
  });

  it("ask passes the 30-per-hour limit on with Retry-After", async () => {
    fakeCoreApi(() => new Response("{}", { status: 429, headers: { "retry-after": "120" } }));
    const response = await ask(browserPost(`/api/subjects/${ID}/documents`, ASKED, SIGNED_IN), params());
    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("120");
    expect(await response.json()).toEqual({ error: "rate_limited" });
  });

  it("confirm calls core-api and answers the document", async () => {
    const calls = fakeCoreApi(() => Response.json({ id: ID, status: "uploaded" }));
    const response = await confirm(browserPost(`/api/documents/${ID}/confirm`, {}, SIGNED_IN), params());
    expect(calls[0].path).toBe(`/v1/documents/${ID}/confirm`);
    expect(response.status).toBe(200);
  });

  it.each([
    [409, "upload_incomplete"],
    [422, "content_mismatch"],
    [422, "size_mismatch"],
    [404, "document_not_found"],
  ])("confirm passes %i %s on", async (status, detail) => {
    fakeCoreApi(() => refusal(status, detail));
    const response = await confirm(browserPost(`/api/documents/${ID}/confirm`, {}, SIGNED_IN), params());
    expect(response.status).toBe(status);
    expect(await response.json()).toEqual({ error: detail });
  });

  it("an unknown refusal is 503 unavailable, and a non-UUID id is 404 without a call", async () => {
    const calls = fakeCoreApi(() => refusal(500, "boom"));
    const down = await confirm(browserPost(`/api/documents/${ID}/confirm`, {}, SIGNED_IN), params());
    const bad = await confirm(browserPost(`/api/documents/x/confirm`, {}, SIGNED_IN), params("x"));
    expect(down.status).toBe(503);
    expect(bad.status).toBe(404);
    expect(calls).toHaveLength(1);
  });
});
