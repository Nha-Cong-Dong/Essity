// T2.15, T2.13 (plan t2.15-t2.13-t2.16-answer-grade.md step 8): the answer screen's routes. Each
// passes one call on to core-api with the user's session, and never lets the browser choose the
// path (only a UUID goes in) or the body (built from the fields read).
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET as readAttempt } from "@/app/api/attempts/[id]/route";
import { PUT as saveDraft } from "@/app/api/attempts/[id]/draft/route";
import { POST as regrade } from "@/app/api/attempts/[id]/regrade/route";
import { POST as submit } from "@/app/api/attempts/[id]/submit/route";
import { POST as openAttempt } from "@/app/api/review-sessions/[id]/attempts/route";
import { GET as current } from "@/app/api/review-sessions/[id]/current/route";
import { POST as stop } from "@/app/api/review-sessions/[id]/stop/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const TOKEN = "session-token-marker-attempts";
const SIGNED_IN = { cookies: { [SESSION_COOKIE]: TOKEN } };
const ID = "6b1c2d3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e";
const params = (id = ID) => ({ params: Promise.resolve({ id }) });
const browserGet = (path: string, options = SIGNED_IN) =>
  browserPost(path, undefined, { ...options, method: "GET" });

const GRADED = {
  status: "submitted",
  grading: "graded",
  failure: null,
  result: { overall: "correct" },
  answer_text: "TCP tin cậy",
  submitted_at: "2026-10-25T03:00:00Z",
  question: { prompt: "TCP?" },
};

describe("answer screen routes (T2.15, T2.13)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  // Red when: the answer does not reach core-api as typed, or the grading is not passed back.
  it("submit passes the answer on and answers what core-api graded", async () => {
    const calls = fakeCoreApi(() => Response.json(GRADED));
    const body = { answer_text: "TCP tin cậy\ndòng hai", dont_remember: false };
    const response = await submit(
      browserPost(`/api/attempts/${ID}/submit`, body, SIGNED_IN),
      params(),
    );
    expect(calls[0].path).toBe(`/v1/attempts/${ID}/submit`);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].body).toEqual(body);
    expect(calls[0].headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(GRADED);
  });

  // Plan D-5. Red when: submitting or "Chấm lại" waits only the default 3 s, so a grading the AI
  // answers in 15 s shows as a failure although it was stored.
  it.each([
    [
      "submit",
      () =>
        submit(
          browserPost(
            `/api/attempts/${ID}/submit`,
            { answer_text: "x", dont_remember: false },
            SIGNED_IN,
          ),
          params(),
        ),
    ],
    [
      "regrade",
      () =>
        regrade(
          browserPost(`/api/attempts/${ID}/regrade`, undefined, SIGNED_IN),
          params(),
        ),
    ],
  ])("%s waits 25 s for core-api", async (_, call) => {
    const timeout = vi.spyOn(AbortSignal, "timeout");
    fakeCoreApi(() => Response.json(GRADED));
    await call();
    expect(timeout).toHaveBeenCalledWith(25_000);
  });

  // US-04 AC3 (plan 🟡15). Red when: an answer of 4000 Vietnamese characters is refused by web's
  // 8 KB body limit before core-api sees it.
  it("an answer of 4000 characters with diacritics goes through", async () => {
    const calls = fakeCoreApi(() => Response.json(GRADED));
    const long = "ữ".repeat(4000);
    const response = await submit(
      browserPost(
        `/api/attempts/${ID}/submit`,
        { answer_text: long, dont_remember: false },
        SIGNED_IN,
      ),
      params(),
    );
    expect(response.status).toBe(200);
    expect(calls[0].body).toEqual({ answer_text: long, dont_remember: false });
  });

  it("a body far past any answer is refused before core-api", async () => {
    const calls = fakeCoreApi(() => Response.json(GRADED));
    const response = await submit(
      browserPost(
        `/api/attempts/${ID}/submit`,
        { answer_text: "x".repeat(70_000), dont_remember: false },
        SIGNED_IN,
      ),
      params(),
    );
    expect(response.status).toBe(400);
    expect(calls).toHaveLength(0);
  });

  it.each([
    [{ answer_text: "x" }],
    [{ answer_text: "x", dont_remember: "no" }],
    [{ answer_text: "x", dont_remember: false, extra: 1 }],
  ])(
    "submit refuses a body other than {answer_text, dont_remember}: %j",
    async (body) => {
      const calls = fakeCoreApi(() => Response.json(GRADED));
      const response = await submit(
        browserPost(`/api/attempts/${ID}/submit`, body, SIGNED_IN),
        params(),
      );
      expect(response.status).toBe(400);
      expect(calls).toHaveLength(0);
    },
  );

  it("the draft is saved with PUT", async () => {
    const calls = fakeCoreApi(() =>
      Response.json({
        id: ID,
        status: "draft",
        answer_text: "x",
        dont_remember: false,
      }),
    );
    const body = { answer_text: "nháp", dont_remember: false };
    const response = await saveDraft(
      browserPost(`/api/attempts/${ID}/draft`, body, {
        ...SIGNED_IN,
        method: "PUT",
      }),
      params(),
    );
    expect(response.status).toBe(200);
    expect(calls[0]).toMatchObject({
      path: `/v1/attempts/${ID}/draft`,
      method: "PUT",
      body,
    });
  });

  // Red when: core-api's 204 (a draft saved, no body) reads as a failure, so every save says
  // "unavailable" and the answer box never shows "Đã lưu nháp".
  it("a draft saved by core-api with 204 answers 204", async () => {
    fakeCoreApi(() => new Response(null, { status: 204 }));
    const response = await saveDraft(
      browserPost(
        `/api/attempts/${ID}/draft`,
        { answer_text: "nháp", dont_remember: false },
        { ...SIGNED_IN, method: "PUT" },
      ),
      params(),
    );
    expect(response.status).toBe(204);
  });

  it("reading an attempt back, and the session's current question", async () => {
    const calls = fakeCoreApi(() => Response.json(GRADED));
    expect(
      (await readAttempt(browserGet(`/api/attempts/${ID}`), params())).status,
    ).toBe(200);
    expect(
      (
        await current(
          browserGet(`/api/review-sessions/${ID}/current`),
          params(),
        )
      ).status,
    ).toBe(200);
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      `GET /v1/attempts/${ID}`,
      `GET /v1/review-sessions/${ID}/current`,
    ]);
  });

  it("opening the current question and stopping are POSTs on the session", async () => {
    const calls = fakeCoreApi((call) =>
      call.path.endsWith("/stop")
        ? Response.json({ answered: 1, total: 2 })
        : Response.json({ id: ID }, { status: 201 }),
    );
    expect(
      (
        await openAttempt(
          browserPost(
            `/api/review-sessions/${ID}/attempts`,
            undefined,
            SIGNED_IN,
          ),
          params(),
        )
      ).status,
    ).toBe(201);
    expect(
      (
        await stop(
          browserPost(`/api/review-sessions/${ID}/stop`, undefined, SIGNED_IN),
          params(),
        )
      ).status,
    ).toBe(200);
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      `POST /v1/review-sessions/${ID}/attempts`,
      `POST /v1/review-sessions/${ID}/stop`,
    ]);
  });

  // Review plan R1. Red when: a path the browser chose reaches core-api.
  it("an id that is not a UUID never reaches core-api", async () => {
    const calls = fakeCoreApi(() => Response.json(GRADED));
    const response = await readAttempt(
      browserGet("/api/attempts/x"),
      params("../me"),
    );
    expect(response.status).toBe(404);
    expect(calls).toHaveLength(0);
  });

  it("no session cookie: signed_out, core-api not called", async () => {
    const calls = fakeCoreApi(() => Response.json(GRADED));
    const response = await regrade(
      browserPost(`/api/attempts/${ID}/regrade`),
      params(),
    );
    expect(response.status).toBe(401);
    expect(calls).toHaveLength(0);
  });

  it("a POST from another site is refused (CSRF)", async () => {
    const calls = fakeCoreApi(() => Response.json(GRADED));
    const response = await submit(
      browserPost(
        `/api/attempts/${ID}/submit`,
        { answer_text: "x", dont_remember: false },
        { ...SIGNED_IN, origin: "https://evil.example" },
      ),
      params(),
    );
    expect(response.status).toBe(403);
    expect(calls).toHaveLength(0);
  });

  it.each([
    [404, "attempt_not_found", 404],
    [409, "session_ended", 409],
    [409, "attempt_not_submitted", 409],
    [422, "answer_empty", 422],
  ])(
    "core-api's %i %s is passed on as its code",
    async (status, detail, expected) => {
      fakeCoreApi(() => Response.json({ detail }, { status }));
      const response = await submit(
        browserPost(
          `/api/attempts/${ID}/submit`,
          { answer_text: "", dont_remember: false },
          SIGNED_IN,
        ),
        params(),
      );
      expect(response.status).toBe(expected);
      expect(await response.json()).toEqual({ error: detail });
    },
  );

  it("an answer core-api refuses by its schema (422 without a code) is invalid_answer", async () => {
    fakeCoreApi(() =>
      Response.json({ detail: [{ type: "string_too_long" }] }, { status: 422 }),
    );
    const response = await submit(
      browserPost(
        `/api/attempts/${ID}/submit`,
        { answer_text: "x", dont_remember: false },
        SIGNED_IN,
      ),
      params(),
    );
    expect(response.status).toBe(422);
    expect(await response.json()).toEqual({ error: "invalid_answer" });
  });

  it("core-api unreachable or timing out: unavailable", async () => {
    fakeCoreApi(() => {
      throw new DOMException("timed out", "TimeoutError");
    });
    const response = await submit(
      browserPost(
        `/api/attempts/${ID}/submit`,
        { answer_text: "x", dont_remember: false },
        SIGNED_IN,
      ),
      params(),
    );
    expect(response.status).toBe(503);
  });
});
