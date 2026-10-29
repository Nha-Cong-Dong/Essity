// T4.13a: the routes behind "Ghi buổi học" (US-02 AC1, AC4, AC7).
import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as confirm } from "@/app/api/sessions/[id]/confirm/route";
import { POST as describeSession } from "@/app/api/subjects/[id]/sessions/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const TOKEN = "session-token-marker-log";
const SIGNED_IN = { cookies: { [SESSION_COOKIE]: TOKEN } };
const ID = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const DOC = "5a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d";
const params = (id = ID) => ({ params: Promise.resolve({ id }) });
const refusal = (status: number, detail: string) => Response.json({ detail }, { status });
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
    ["notes (T4.13b)", { ranges: [], notes: [] }],
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
});
