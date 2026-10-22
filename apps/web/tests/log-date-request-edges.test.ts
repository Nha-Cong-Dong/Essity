// T1.21 edge cases the Tester found open (feature-tester, 23/10). Each test says which change to
// the source turns it red.
import { afterEach, describe, expect, it, vi } from "vitest";

import { postJson } from "@/lib/auth-errors";
import { exampleFor, learningDay } from "@/lib/exam-date";
import { errorName, logError } from "@/lib/log";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

function logged(): () => Record<string, unknown>[] {
  const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
  return () => spy.mock.calls.map(([line]) => JSON.parse(String(line)) as Record<string, unknown>);
}

describe("logError edges (R12)", () => {
  // Red when: the loop tests `if (fields[name])` (truthiness): status 0, a network failure, would
  // vanish from the line.
  it("keeps status 0 and leaves out a field that is undefined", () => {
    const lines = logged();
    logError("core-api call failed", { route: "login", status: 0, error: undefined });
    const [line] = lines();
    expect(line.status).toBe(0);
    expect("error" in line).toBe(false);
  });

  // Red when: fields are merged over the line (Object.assign / spread after the base): a caller
  // could then rewrite level, service or message, or hide an ERROR as INFO.
  it("fields cannot overwrite level, service, message or timestamp", () => {
    const lines = logged();
    const hostile = { level: "INFO", service: "other", message: "x", timestamp: "never" };
    logError("core-api call failed", hostile as Parameters<typeof logError>[1]);
    const [line] = lines();
    expect(line).toMatchObject({ level: "ERROR", service: "web", message: "core-api call failed" });
    expect(line.timestamp).not.toBe("never");
  });

  // Red when: errorName returns the message (it may quote a URL or a body) or throws on a
  // non-Error (promise rejections often carry strings, and null).
  it("errorName is the type of an Error and nothing else", () => {
    expect(errorName(new TypeError("https://core-api/secret-token-123"))).toBe("TypeError");
    expect(errorName("a string with a secret")).toBeUndefined();
    expect(errorName(null)).toBeUndefined();
    expect(errorName(undefined)).toBeUndefined();
  });

  // Red when: logError writes a made-up trace_id/span_id (an empty or all-zero one) when no
  // span is active.
  it("a line outside any span has no trace_id", () => {
    const lines = logged();
    logError("core-api call failed");
    const [line] = lines();
    expect("trace_id" in line).toBe(false);
    expect("span_id" in line).toBe(false);
  });
});

describe("learningDay across calendar edges (R24)", () => {
  // Red when: the "before dayStartHour, yesterday" step stops using calendar arithmetic (a
  // fixed 24 h, or a day number minus one) and breaks at a month, year or leap-day boundary.
  it.each([
    ["2028-02-29T17:00:00Z", "Asia/Ho_Chi_Minh", 4, "2028-02-29"], // 00:00 on 1 March, leap year
    ["2027-02-28T17:00:00Z", "Asia/Ho_Chi_Minh", 4, "2027-02-28"], // 00:00 on 1 March, not leap
    ["2026-12-31T20:00:00Z", "Asia/Ho_Chi_Minh", 4, "2026-12-31"], // 03:00 on 1 January
    ["2026-12-31T21:00:00Z", "Asia/Ho_Chi_Minh", 4, "2027-01-01"], // 04:00 on 1 January
    ["2026-12-31T23:59:59Z", "UTC", 0, "2026-12-31"],
    ["2027-01-01T00:00:00Z", "UTC", 0, "2027-01-01"], // local midnight must read 0, not 24
  ])("%s in %s, day starting at %i → %s", (instant, zone, hour, day) => {
    expect(learningDay(new Date(instant), zone, hour)).toBe(day);
  });
});

describe("exampleFor edges (R24)", () => {
  // Red when: the catch is removed (a bad zone from /v1/me crashes the page) or falls back to a
  // date that may be today.
  it.each(["", "UTC+7", "Asia/Saigon-typo", "  "])("a bad zone %j gives next year's example", (zone) => {
    expect(exampleFor(new Date("2026-06-01T00:00:00Z"), zone, 4)).toBe("15/12/2027");
  });

  // Red when: the example ignores the user's day start and uses the calendar day: one hour
  // earlier (03:59 local on 15/12) 15/12/2026 is still accepted by core-api as a future date.
  it("the same instant gives different examples for a day start of 0 and of 4", () => {
    const instant = new Date("2026-12-14T20:30:00Z"); // 03:30 on 15/12 in Vietnam
    expect(exampleFor(instant, "Asia/Ho_Chi_Minh", 4)).toBe("15/12/2026");
    expect(exampleFor(instant, "Asia/Ho_Chi_Minh", 0)).toBe("15/12/2027");
  });
});

describe("postJson edges (R22)", () => {
  function reply(response: Response) {
    vi.stubGlobal("fetch", vi.fn(async () => response));
  }

  // Red when: an array body of an error status is passed on as `body` (the form would read
  // fields off a list) or as an error code.
  it("an error with a JSON array body has no body and is unavailable", async () => {
    reply(Response.json([{ error: "x" }], { status: 400 }));
    const result = await postJson("/api/auth/login", {});
    expect(result.body).toBeUndefined();
    expect(result.error).toBe("unavailable");
  });

  // Red when: Retry-After is read with parseInt or Number without a fallback: "soon" gives NaN
  // and the countdown shows NaN minutes.
  it("a Retry-After that is not a number is ignored", async () => {
    reply(Response.json({ error: "rate_limited" }, { status: 429, headers: { "retry-after": "soon" } }));
    const result = await postJson("/api/auth/login", {});
    expect(result.status).toBe(429);
    expect(result.retryAfter).toBeUndefined();
  });

  it("a Retry-After in seconds is passed on", async () => {
    reply(Response.json({ error: "rate_limited" }, { status: 429, headers: { "retry-after": "120" } }));
    expect((await postJson("/api/auth/login", {})).retryAfter).toBe(120);
  });

  // Red when: a network failure stops being status 0 / unavailable (the try/catch is removed).
  it("a network failure is status 0, unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("fetch failed"))));
    expect(await postJson("/api/auth/login", {})).toEqual({ status: 0, error: "unavailable" });
  });
});
