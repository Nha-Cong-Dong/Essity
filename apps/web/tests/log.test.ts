// Risk register R12, ADR-0013: web's log lines are JSON, carry the trace, and hold only the
// fields web may log (never a message, a body, an email or a token).
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { trace } from "@opentelemetry/api";
import { afterEach, describe, expect, it, vi } from "vitest";

import { logError } from "@/lib/log";

const ROOT = path.resolve(import.meta.dirname, "..");

afterEach(() => vi.restoreAllMocks());

function captured(): () => Record<string, unknown>[] {
  const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
  return () => spy.mock.calls.map(([line]) => JSON.parse(String(line)) as Record<string, unknown>);
}

describe("logError (R12)", () => {
  // Red when: lib/log.ts does not exist or writes something other than one JSON object.
  it("writes one JSON line with service, level and message", () => {
    const lines = captured();
    logError("core-api call failed", { route: "subjects", status: 503, error: "CoreStatusError" });
    expect(lines()).toEqual([
      expect.objectContaining({
        service: "web",
        level: "ERROR",
        message: "core-api call failed",
        route: "subjects",
        status: 503,
        error: "CoreStatusError",
      }),
    ]);
  });

  // Red when: a field outside the list (an email, a body) reaches the line.
  it("keeps only the fields it allows", () => {
    const lines = captured();
    const fields = { route: "baseline", email: "a@example.com", body: "gpa=3.2" };
    logError("core-api call failed", fields as Parameters<typeof logError>[1]);
    const [line] = lines();
    expect(line.route).toBe("baseline");
    expect(JSON.stringify(line)).not.toMatch(/a@example\.com|gpa=3\.2/);
  });

  // Red when: the line is not joined to the request's trace (ADR-0013).
  it("carries the active span's trace_id", () => {
    const lines = captured();
    const span = trace.wrapSpanContext({
      traceId: "0af7651916cd43dd8448eb211c80319c",
      spanId: "b7ad6b7169203331",
      traceFlags: 1,
    });
    // The real request span comes from instrumentation.node.ts; here, the one getActiveSpan sees.
    vi.spyOn(trace, "getActiveSpan").mockReturnValue(span);
    logError("core-api call failed");
    expect(lines()[0]).toEqual(
      expect.objectContaining({ trace_id: "0af7651916cd43dd8448eb211c80319c", span_id: "b7ad6b7169203331" }),
    );
  });
});

describe("no console outside lib/log.ts (R12)", () => {
  function sources(dir: string): string[] {
    return readdirSync(path.join(ROOT, dir), { recursive: true, encoding: "utf-8" })
      .filter((file) => /\.(ts|tsx)$/.test(file))
      .map((file) => path.join(dir, file).replaceAll("\\", "/"));
  }

  // Red when: a console call is added anywhere but lib/log.ts (it would skip the JSON shape
  // and the allowed fields).
  it("app/, components/, lib/ and instrumentation.ts", () => {
    const files = [...["app", "components", "lib"].flatMap(sources), "instrumentation.ts"];
    const offenders = files.filter(
      (file) => file !== "lib/log.ts" && /\bconsole\./.test(readFileSync(path.join(ROOT, file), "utf-8")),
    );
    expect(offenders).toEqual([]);
  });
});
