// T1.20: web's routes behind the subject screens (US-01 AC1, AC2; review plan R1).
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PATCH } from "@/app/api/subjects/[id]/route";
import { POST } from "@/app/api/subjects/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const TOKEN = "session-token-marker-subjects";
const SIGNED_IN = { cookies: { [SESSION_COOKIE]: TOKEN } };
const ID = "3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b";
const NAME_MARKER = "Mạng máy tính marker-71c";
const SUBJECT = {
  id: ID,
  name: NAME_MARKER,
  exam_date: "2026-12-15",
  days_until_exam: 54,
  created_at: "2026-10-22T05:00:00Z",
};

const patch = (id: string, body: unknown, options: Parameters<typeof browserPost>[2] = SIGNED_IN) =>
  PATCH(browserPost(`/api/subjects/${id}`, body, { ...options, method: "PATCH" }), {
    params: Promise.resolve({ id }),
  });

describe("POST /api/subjects (T1.20)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it("US-01 AC1: sends exactly name and exam_date, with the session, and answers the new id", async () => {
    const calls = fakeCoreApi(() => Response.json(SUBJECT, { status: 201 }));

    const response = await POST(
      browserPost("/api/subjects", { name: NAME_MARKER, exam_date: "2026-12-15" }, SIGNED_IN),
    );

    expect(calls).toHaveLength(1);
    expect(calls[0].path).toBe("/v1/subjects");
    expect(calls[0].body).toEqual({ name: NAME_MARKER, exam_date: "2026-12-15" });
    expect(calls[0].headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(response.status).toBe(201);
    expect(await response.json()).toEqual({ id: ID });
  });

  it("US-01 AC2: exam_date_not_in_future is passed on as its code", async () => {
    fakeCoreApi(() => Response.json({ detail: "exam_date_not_in_future" }, { status: 422 }));

    const response = await POST(
      browserPost("/api/subjects", { name: "Mạng", exam_date: "2026-10-01" }, SIGNED_IN),
    );

    expect(response.status).toBe(422);
    expect(await response.json()).toEqual({ error: "exam_date_not_in_future" });
  });

  it("plan K17: exam_date_too_far is passed on as its code", async () => {
    fakeCoreApi(() => Response.json({ detail: "exam_date_too_far" }, { status: 422 }));

    const response = await POST(
      browserPost("/api/subjects", { name: "Mạng", exam_date: "2062-12-15" }, SIGNED_IN),
    );

    expect(response.status).toBe(422);
    expect(await response.json()).toEqual({ error: "exam_date_too_far" });
  });

  it.each([
    [["body", "name"], ["name"]],
    [["body", "exam_date"], ["exam_date"]],
  ])("core-api's 422 at %j names %j and never echoes the input", async (loc, fields) => {
    fakeCoreApi(() =>
      Response.json(
        { detail: [{ loc, type: "string_too_long", msg: "bad", input: NAME_MARKER, ctx: { max: 200 } }] },
        { status: 422 },
      ),
    );

    const response = await POST(
      browserPost("/api/subjects", { name: NAME_MARKER, exam_date: "2026-12-15" }, SIGNED_IN),
    );

    const text = await response.text();
    expect(JSON.parse(text)).toEqual({ error: "invalid", fields });
    expect(text).not.toContain(NAME_MARKER);
  });

  // Red when: the route passes on the browser's JSON (review plan R1).
  it.each([
    { name: "Mạng", exam_date: "2026-12-15", user_id: "u2" },
    { name: 42, exam_date: "2026-12-15" },
    { name: "Mạng" },
  ])("review plan R1: a body of the wrong shape is refused before core-api: %j", async (body) => {
    const calls = fakeCoreApi(() => Response.json(SUBJECT, { status: 201 }));

    const response = await POST(browserPost("/api/subjects", body, SIGNED_IN));

    expect(response.status).toBe(400);
    expect(calls).toHaveLength(0);
  });

  it("without a session cookie: 401 signed_out, core-api not asked", async () => {
    const calls = fakeCoreApi(() => Response.json(SUBJECT, { status: 201 }));

    const response = await POST(browserPost("/api/subjects", { name: "Mạng", exam_date: "2026-12-15" }));

    expect(response.status).toBe(401);
    expect(calls).toHaveLength(0);
  });

  it("ADR-0013: core-api down → 503, and the subject name is in no log line", async () => {
    const logged = vi.spyOn(console, "error").mockImplementation(() => undefined);
    fakeCoreApi(() => {
      throw new TypeError(`fetch failed ${NAME_MARKER}`);
    });

    const response = await POST(
      browserPost("/api/subjects", { name: NAME_MARKER, exam_date: "2026-12-15" }, SIGNED_IN),
    );

    expect(response.status).toBe(503);
    expect(JSON.stringify(logged.mock.calls)).not.toContain(NAME_MARKER);
  });
});

describe("PATCH /api/subjects/[id] (T1.20, plan K2)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it("sends only the fields given and answers the subject", async () => {
    const calls = fakeCoreApi(() => Response.json({ ...SUBJECT, exam_date: "2026-12-20", days_until_exam: 59 }));

    const response = await patch(ID, { exam_date: "2026-12-20" });

    expect(calls[0].method).toBe("PATCH");
    expect(calls[0].path).toBe(`/v1/subjects/${ID}`);
    expect(calls[0].body).toEqual({ exam_date: "2026-12-20" });
    expect(await response.json()).toEqual({
      subject: { id: ID, name: NAME_MARKER, exam_date: "2026-12-20", days_until_exam: 59 },
    });
  });

  // Red when: the id goes into the path unchecked: "..", "%2e%2e" or a slash would reach another
  // core-api endpoint (review plan R1).
  it.each(["..", "%2e%2e", "../me", "not-a-uuid", `${ID}/x`, ""])(
    "review plan R1: id %j is 404 subject_not_found, core-api not asked",
    async (id) => {
      const calls = fakeCoreApi(() => Response.json(SUBJECT));

      const response = await patch(id, { name: "Mạng" });

      expect(response.status).toBe(404);
      expect(await response.json()).toEqual({ error: "subject_not_found" });
      expect(calls).toHaveLength(0);
    },
  );

  it("ADR-0001: someone else's subject (core-api 404) is subject_not_found", async () => {
    fakeCoreApi(() => Response.json({ detail: "subject_not_found" }, { status: 404 }));

    const response = await patch(ID, { name: "Mạng" });

    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "subject_not_found" });
  });

  it("US-01 AC2: exam_date_not_in_future is passed on", async () => {
    fakeCoreApi(() => Response.json({ detail: "exam_date_not_in_future" }, { status: 422 }));

    const response = await patch(ID, { exam_date: "2026-10-01" });

    expect(await response.json()).toEqual({ error: "exam_date_not_in_future" });
  });

  it("plan K17: exam_date_too_far is passed on", async () => {
    fakeCoreApi(() => Response.json({ detail: "exam_date_too_far" }, { status: 422 }));

    const response = await patch(ID, { exam_date: "2062-12-15" });

    expect(await response.json()).toEqual({ error: "exam_date_too_far" });
  });

  it.each([{}, { name: "Mạng", extra: 1 }, { name: null }, { exam_date: 20261220 }])(
    "review plan R1: body %j is refused before core-api",
    async (body) => {
      const calls = fakeCoreApi(() => Response.json(SUBJECT));

      const response = await patch(ID, body);

      expect(response.status).toBe(400);
      expect(calls).toHaveLength(0);
    },
  );

  it("ADR-0014: another origin is refused", async () => {
    const calls = fakeCoreApi(() => Response.json(SUBJECT));

    const response = await patch(ID, { name: "Mạng" }, { ...SIGNED_IN, origin: "https://evil.example" });

    expect(response.status).toBe(403);
    expect(calls).toHaveLength(0);
  });
});
