// T2.19 (US-09 AC1, AC4): the routes behind "Chấm sai" and "Bỏ câu này". Each passes one call to
// core-api for the signed-in user, with only a UUID in the path and a body built from the fields.
import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as override } from "@/app/api/grades/[id]/override/route";
import { POST as drop } from "@/app/api/questions/[id]/drop/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const TOKEN = "session-token-marker-override";
const SIGNED_IN = { cookies: { [SESSION_COOKIE]: TOKEN } };
const ID = "a1b2c3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d";
const params = (id = ID) => ({ params: Promise.resolve({ id }) });
const refusal = (status: number, detail: string) => Response.json({ detail }, { status });

describe("override route (T2.19)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  // Red when: the verdict is not passed as chosen, or the answer is not passed back.
  it("US-09 AC1: passes the verdict on and answers the attempt", async () => {
    const calls = fakeCoreApi(() => Response.json({ grading: "graded" }));
    const response = await override(
      browserPost(`/api/grades/${ID}/override`, { verdict: "correct" }, SIGNED_IN),
      params(),
    );
    expect(calls[0].path).toBe(`/v1/grades/${ID}/override`);
    expect(calls[0].body).toEqual({ verdict: "correct" });
    expect(calls[0].headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(response.status).toBe(200);
  });

  // Red when: a third verdict ("partial", "forgot", anything) reaches core-api.
  it.each(["partial", "forgot", "", 1])("US-09 AC1: verdict %j is 400 without a call", async (verdict) => {
    const calls = fakeCoreApi(() => Response.json({}));
    const response = await override(browserPost(`/api/grades/${ID}/override`, { verdict }, SIGNED_IN), params());
    expect(response.status).toBe(400);
    expect(calls).toHaveLength(0);
  });

  it("an extra field is 400 and a non-UUID id is 404, both without a call", async () => {
    const calls = fakeCoreApi(() => Response.json({}));
    const extra = await override(
      browserPost(`/api/grades/${ID}/override`, { verdict: "correct", user_id: "x" }, SIGNED_IN),
      params(),
    );
    const bad = await override(
      browserPost(`/api/grades/../override`, { verdict: "correct" }, SIGNED_IN),
      params("../x"),
    );
    expect(extra.status).toBe(400);
    expect(bad.status).toBe(404);
    expect(calls).toHaveLength(0);
  });

  it("signed out is 401 without a call", async () => {
    const calls = fakeCoreApi(() => Response.json({}));
    const response = await override(
      browserPost(`/api/grades/${ID}/override`, { verdict: "correct" }, { cookies: {} }),
      params(),
    );
    expect(response.status).toBe(401);
    expect(calls).toHaveLength(0);
  });

  // Red when: core-api's refusal turns into a generic failure, so the screen cannot tell them apart.
  it.each([
    [404, "grade_not_found"],
    [409, "grade_not_current"],
    [409, "grading_in_progress"],
  ])("core-api %i %s goes through with its code", async (status, detail) => {
    fakeCoreApi(() => refusal(status, detail));
    const response = await override(
      browserPost(`/api/grades/${ID}/override`, { verdict: "incorrect" }, SIGNED_IN),
      params(),
    );
    expect(response.status).toBe(status);
    expect(await response.json()).toEqual({ error: detail });
  });
});

describe("drop route (T2.19)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it("US-09 AC4: one POST to core-api, 204 back", async () => {
    const calls = fakeCoreApi(() => new Response(null, { status: 204 }));
    const response = await drop(browserPost(`/api/questions/${ID}/drop`, undefined, SIGNED_IN), params());
    expect(calls[0].path).toBe(`/v1/questions/${ID}/drop`);
    expect(calls[0].method).toBe("POST");
    expect(response.status).toBe(204);
  });

  it("core-api 404 question_not_found goes through with its code", async () => {
    fakeCoreApi(() => refusal(404, "question_not_found"));
    const response = await drop(browserPost(`/api/questions/${ID}/drop`, undefined, SIGNED_IN), params());
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "question_not_found" });
  });

  it("a non-UUID id is 404 without a call", async () => {
    const calls = fakeCoreApi(() => new Response(null, { status: 204 }));
    const response = await drop(browserPost(`/api/questions/x/drop`, undefined, SIGNED_IN), params("../x"));
    expect(response.status).toBe(404);
    expect(calls).toHaveLength(0);
  });
});
