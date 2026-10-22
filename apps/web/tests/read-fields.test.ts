// Review plan R1: web's routes read a JSON body by a schema and build what they send themselves.
import { describe, expect, it } from "vitest";

import { readFields } from "@/lib/http";

import { browserPost } from "./helpers";

const SCHEMA = {
  gpa_before: { kind: "string" },
  prior_ready_days: { kind: "integer", optional: true },
  prior_days_unknown: { kind: "boolean" },
} as const;

const read = (body: unknown) => readFields(browserPost("/api/baseline", body), SCHEMA);

describe("readFields (review plan R1)", () => {
  it("returns the fields with their types", async () => {
    expect(await read({ gpa_before: "2.85", prior_ready_days: 3, prior_days_unknown: false })).toEqual({
      gpa_before: "2.85",
      prior_ready_days: 3,
      prior_days_unknown: false,
    });
  });

  it("leaves an optional field out when it is missing", async () => {
    expect(await read({ gpa_before: "2.85", prior_days_unknown: true })).toEqual({
      gpa_before: "2.85",
      prior_days_unknown: true,
    });
  });

  // Red when: a field of the wrong type is passed on, and core-api's 422 lands on the wrong field.
  it.each([
    { gpa_before: 2.85, prior_ready_days: 3, prior_days_unknown: false },
    { gpa_before: "2.85", prior_ready_days: "5", prior_days_unknown: false },
    { gpa_before: "2.85", prior_ready_days: 1.5, prior_days_unknown: false },
    { gpa_before: "2.85", prior_ready_days: 3, prior_days_unknown: "true" },
    { gpa_before: "2.85", prior_ready_days: null, prior_days_unknown: false },
    { prior_ready_days: 3, prior_days_unknown: false },
  ])("refuses a field of the wrong type or a missing one: %j", async (body) => {
    expect(await read(body)).toBeNull();
  });

  // Red when: unknown keys are passed on (they would reach core-api's extra=forbid as a 422).
  it("refuses a key it does not know", async () => {
    expect(await read({ gpa_before: "2.85", prior_days_unknown: true, entered_at: "2020-01-01" })).toBeNull();
  });

  it.each([[["a"]], ["text"], [null]])("refuses a body that is not an object: %j", async (body) => {
    expect(await read(body)).toBeNull();
  });
});
