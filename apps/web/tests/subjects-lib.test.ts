// T1.20: subjects read on the server for /subjects and /subjects/[id]/upload (plan K5; review plan R1).
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fakeCoreApi, SERVICE_TOKEN } from "./helpers";

const TOKEN = "session-token-marker-subjects-lib";
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => (name === "__Host-essity_session" ? { name, value: TOKEN } : undefined),
  }),
}));

const { CoreStatusError, findSubject, isSubjectId, listSubjects } = await import("@/lib/subjects");

const ID = "3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b";
const MMT = { id: ID, name: "Mạng máy tính", exam_date: "2026-12-15", days_until_exam: 54, created_at: "x" };

describe("subjects on the server", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it("listSubjects asks core-api with the session", async () => {
    const calls = fakeCoreApi(() => Response.json([MMT]));

    expect(await listSubjects()).toEqual([MMT]);
    expect(calls[0].path).toBe("/v1/subjects");
    expect(calls[0].headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
  });

  // Red when: every failure looks alike, and a dead session reads as a network error (review c469b4d #1).
  it.each([401, 500])("listSubjects throws a CoreStatusError carrying %i", async (status) => {
    fakeCoreApi(() => new Response("", { status }));

    const error = await listSubjects().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(CoreStatusError);
    expect((error as InstanceType<typeof CoreStatusError>).status).toBe(status);
  });

  it("plan K5: findSubject picks the subject by id", async () => {
    fakeCoreApi(() => Response.json([MMT]));

    expect(await findSubject(ID)).toEqual(MMT);
  });

  it("plan K5: a subject that is not the user's is null (404 on the page)", async () => {
    fakeCoreApi(() => Response.json([MMT]));

    expect(await findSubject("0f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b")).toBeNull();
  });

  // Red when: an id from the URL reaches core-api unchecked (review plan R1).
  it.each(["..", "%2e%2e", "abc", `${ID}/x`])("review plan R1: id %j is null without asking core-api", async (id) => {
    const calls = fakeCoreApi(() => Response.json([MMT]));

    expect(await findSubject(id)).toBeNull();
    expect(calls).toHaveLength(0);
  });

  it.each([
    [ID, true],
    [ID.toUpperCase(), true],
    ["..", false],
    ["", false],
  ])("isSubjectId(%j) is %s", (id, ok) => {
    expect(isSubjectId(id)).toBe(ok);
  });
});
