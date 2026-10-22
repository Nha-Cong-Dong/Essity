// T1.18: web's routes behind the baseline screen (US-11; plan K4c, K4d; review plan R1, R3).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST as skip } from "@/app/api/baseline/skip/route";
import { POST as save } from "@/app/api/baseline/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const TOKEN = "session-token-marker-baseline";
const SIGNED_IN = { cookies: { [SESSION_COOKIE]: TOKEN } };
const GPA_MARKER = "3.17";
const BODY = { gpa_before: GPA_MARKER, prior_ready_days: 3, prior_days_unknown: false };

const ME = {
  id: "u1",
  email: "a@example.com",
  email_verified: true,
  timezone: "Asia/Ho_Chi_Minh",
  day_start_hour: 4,
  needs_baseline: false,
  has_subjects: false,
};

const BASELINE_OUT = {
  gpa_before: GPA_MARKER,
  prior_ready_days: 3,
  prior_days_unknown: false,
  entered_at: "2026-10-22T05:00:00Z",
  is_late: false,
  locked: false,
  editable_until: "2026-10-29T05:00:00Z",
};

/** core-api: the baseline call answers `baseline`; /v1/me answers `me` (or fails). */
function core({ baseline, me = Response.json(ME) }: { baseline: () => Response; me?: Response | (() => Response) }) {
  return fakeCoreApi((call) => {
    if (call.path === "/v1/me") return typeof me === "function" ? me() : me.clone();
    return baseline();
  });
}

describe("POST /api/baseline (T1.18)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("US-11 AC1: forwards exactly gpa_before, prior_ready_days, prior_days_unknown with the session", async () => {
    const calls = core({ baseline: () => Response.json(BASELINE_OUT, { status: 201 }) });

    await save(browserPost("/api/baseline", BODY, SIGNED_IN));

    const sent = calls.find((call) => call.path === "/v1/baseline");
    expect(sent?.method).toBe("POST");
    expect(sent?.body).toEqual(BODY);
    expect(sent?.headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
  });

  it('US-11 AC1: "Không nhớ" is sent without a day count', async () => {
    const calls = core({ baseline: () => Response.json(BASELINE_OUT, { status: 201 }) });

    await save(browserPost("/api/baseline", { gpa_before: "2.5", prior_days_unknown: true }, SIGNED_IN));

    expect(calls.find((call) => call.path === "/v1/baseline")?.body).toEqual({
      gpa_before: "2.5",
      prior_days_unknown: true,
    });
  });

  it.each([
    [false, "/subjects/new"],
    [true, "/today"],
  ])("plan K4c: saved, has_subjects %s → next %s", async (hasSubjects, next) => {
    core({
      baseline: () => Response.json(BASELINE_OUT, { status: 201 }),
      me: Response.json({ ...ME, has_subjects: hasSubjects }),
    });

    const response = await save(browserPost("/api/baseline", BODY, SIGNED_IN));

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ next });
  });

  // Red when: a second tab's 409 shows an error, though the baseline the user wanted is there.
  it("plan K4d: 409 baseline_already_exists carries on like a save", async () => {
    core({ baseline: () => Response.json({ detail: "baseline_already_exists" }, { status: 409 }) });

    const response = await save(browserPost("/api/baseline", BODY, SIGNED_IN));

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ next: "/subjects/new" });
  });

  // Red when: a failed /v1/me after a save turns into an error that asks to save again.
  it("review plan R3: saved, then /v1/me fails → next /today", async () => {
    core({
      baseline: () => Response.json(BASELINE_OUT, { status: 201 }),
      me: () => new Response("", { status: 503 }),
    });

    const response = await save(browserPost("/api/baseline", BODY, SIGNED_IN));

    expect(await response.json()).toEqual({ next: "/today" });
  });

  it.each([
    [["body", "gpa_before"], ["gpa_before"]],
    [["body", "prior_ready_days"], ["prior_ready_days"]],
    [["body"], []],
  ])("US-11 AC3: core-api's 422 at %j names field(s) %j and never echoes the value", async (loc, fields) => {
    core({
      baseline: () =>
        Response.json({ detail: [{ loc, type: "less_than_equal", msg: "bad" }] }, { status: 422 }),
    });

    const response = await save(browserPost("/api/baseline", BODY, SIGNED_IN));

    expect(response.status).toBe(422);
    const text = await response.text();
    expect(JSON.parse(text)).toEqual({ error: "invalid", fields });
    expect(text).not.toContain(GPA_MARKER);
  });

  // Red when: the route passes on the browser's JSON as it is (review plan R1).
  it.each([
    { ...BODY, prior_ready_days: "5" },
    { ...BODY, entered_at: "2020-01-01T00:00:00Z" },
    { ...BODY, gpa_before: 3.17 },
  ])("review plan R1: a body of the wrong shape is refused before core-api: %j", async (body) => {
    const calls = core({ baseline: () => Response.json(BASELINE_OUT, { status: 201 }) });

    const response = await save(browserPost("/api/baseline", body, SIGNED_IN));

    expect(response.status).toBe(400);
    expect(calls).toHaveLength(0);
  });

  it("without a session cookie: 401 signed_out, core-api not asked", async () => {
    const calls = core({ baseline: () => Response.json(BASELINE_OUT, { status: 201 }) });

    const response = await save(browserPost("/api/baseline", BODY));

    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ error: "signed_out" });
    expect(calls).toHaveLength(0);
  });

  it("a session core-api no longer knows: 401 signed_out", async () => {
    core({ baseline: () => new Response("", { status: 401 }) });

    const response = await save(browserPost("/api/baseline", BODY, SIGNED_IN));

    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ error: "signed_out" });
  });

  // Red when: a failure is logged with the request (GPA is personal data, ADR-0013).
  it("ADR-0013: core-api down → 503, and the GPA is in no log line", async () => {
    const logged = vi.spyOn(console, "error").mockImplementation(() => undefined);
    fakeCoreApi(() => {
      throw new TypeError(`fetch failed ${GPA_MARKER}`);
    });

    const response = await save(browserPost("/api/baseline", BODY, SIGNED_IN));

    expect(response.status).toBe(503);
    expect(JSON.stringify(logged.mock.calls)).not.toContain(GPA_MARKER);
  });

  it("ADR-0014: another origin is refused", async () => {
    const calls = core({ baseline: () => Response.json(BASELINE_OUT, { status: 201 }) });

    const response = await save(browserPost("/api/baseline", BODY, { ...SIGNED_IN, origin: "https://evil.example" }));

    expect(response.status).toBe(403);
    expect(calls).toHaveLength(0);
  });
});

describe("POST /api/baseline/skip (T1.18, US-11 AC2)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it.each([
    [false, "/subjects/new"],
    [true, "/today"],
  ])("AC2: records the skip, then has_subjects %s → next %s (never back to /onboarding)", async (hasSubjects, next) => {
    const calls = core({
      baseline: () => Response.json({ needs_baseline: true }),
      me: Response.json({ ...ME, needs_baseline: true, has_subjects: hasSubjects }),
    });

    const response = await skip(browserPost("/api/baseline/skip", undefined, SIGNED_IN));

    expect(calls.find((call) => call.path === "/v1/baseline/skip")?.method).toBe("POST");
    expect(await response.json()).toEqual({ next });
  });

  it("without a session cookie: 401 signed_out", async () => {
    const calls = core({ baseline: () => Response.json({ needs_baseline: true }) });

    const response = await skip(browserPost("/api/baseline/skip", undefined));

    expect(response.status).toBe(401);
    expect(calls).toHaveLength(0);
  });

  it("core-api down: 503", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    fakeCoreApi(() => new Response("", { status: 500 }));

    const response = await skip(browserPost("/api/baseline/skip", undefined, SIGNED_IN));

    expect(response.status).toBe(503);
  });
});
