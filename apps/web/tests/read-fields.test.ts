// Review plan R1: web's routes read a JSON body by a schema and build what they send themselves.
import { describe, expect, it } from "vitest";

import { readFields } from "@/lib/http";

import { browserPost } from "./helpers";

const SCHEMA = {
  name: { kind: "string" },
  days_left: { kind: "integer", optional: true },
  archived: { kind: "boolean" },
} as const;

const read = (body: unknown) => readFields(browserPost("/api/subjects", body), SCHEMA);

describe("readFields (review plan R1)", () => {
  it("returns the fields with their types", async () => {
    expect(await read({ name: "Mạng", days_left: 3, archived: false })).toEqual({
      name: "Mạng",
      days_left: 3,
      archived: false,
    });
  });

  it("leaves an optional field out when it is missing", async () => {
    expect(await read({ name: "Mạng", archived: true })).toEqual({
      name: "Mạng",
      archived: true,
    });
  });

  // Red when: a field of the wrong type is passed on, and core-api's 422 lands on the wrong field.
  it.each([
    { name: 2, days_left: 3, archived: false },
    { name: "Mạng", days_left: "5", archived: false },
    { name: "Mạng", days_left: 1.5, archived: false },
    { name: "Mạng", days_left: 3, archived: "true" },
    { name: "Mạng", days_left: null, archived: false },
    { days_left: 3, archived: false },
  ])("refuses a field of the wrong type or a missing one: %j", async (body) => {
    expect(await read(body)).toBeNull();
  });

  // Red when: unknown keys are passed on (they would reach core-api's extra=forbid as a 422).
  it("refuses a key it does not know", async () => {
    expect(await read({ name: "Mạng", archived: true, entered_at: "2020-01-01" })).toBeNull();
  });

  it.each([[["a"]], ["text"], [null]])("refuses a body that is not an object: %j", async (body) => {
    expect(await read(body)).toBeNull();
  });
});
