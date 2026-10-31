// T7.5: the routes behind the syllabus screen and the role choice (US-01 AC4, AC5; US-13 AC4).
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET as readDocument, PATCH as patchDocument } from "@/app/api/documents/[id]/route";
import { PATCH as patchSection } from "@/app/api/sections/[id]/route";
import { GET as readOutline } from "@/app/api/subjects/[id]/outline/route";
import { PUT as putTextbook } from "@/app/api/subjects/[id]/textbook/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const TOKEN = "session-token-marker-outline";
const SIGNED_IN = { cookies: { [SESSION_COOKIE]: TOKEN } };
const ID = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const DOC = "c3d4e5f6-7a8b-4c9d-8e1f-2a3b4c5d6e7f";
const params = (id = ID) => ({ params: Promise.resolve({ id }) });
const send = (method: string, path: string, body?: unknown, auth: { cookies: Record<string, string> } = SIGNED_IN) =>
  browserPost(path, body, { ...auth, method });
const refusal = (status: number, body: object) => Response.json(body, { status });

describe("outline routes (T7.5)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  // Red when: the section body is not rebuilt, or the session is not passed on.
  it("US-13 AC4: PATCH a section passes the range on and answers the outline", async () => {
    const calls = fakeCoreApi(() => Response.json({ sections: [] }));
    const response = await patchSection(
      send("PATCH", `/api/sections/${ID}`, { first_page: 3, last_page: 9 }),
      params(),
    );
    expect(calls[0].path).toBe(`/v1/sections/${ID}`);
    expect(calls[0].body).toEqual({ first_page: 3, last_page: 9 });
    expect(calls[0].headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(response.status).toBe(200);
  });

  it("US-13 AC4: PATCH a section refuses another field, an empty body, a bad id or no session without a call", async () => {
    const calls = fakeCoreApi(() => Response.json({}));
    const statuses = [
      (await patchSection(send("PATCH", "/x", { title: "x" }), params())).status,
      (await patchSection(send("PATCH", "/x", {}), params())).status,
      (await patchSection(send("PATCH", "/x", { studied: true }), params("../x"))).status,
      (await patchSection(send("PATCH", "/x", { studied: true }, { cookies: {} }), params())).status,
      (await patchSection(send("PATCH", "/x", { studied: "yes" }), params())).status,
    ];
    expect(statuses).toEqual([400, 400, 404, 401, 400]);
    expect(calls).toHaveLength(0);
  });

  it.each(["invalid_range", "outside_parent", "children_outside", "outside_document", "nothing_to_change"])(
    "US-13 AC4: core-api's 422 %s is passed on as its code",
    async (detail) => {
      fakeCoreApi(() => refusal(422, { detail }));
      const response = await patchSection(send("PATCH", "/x", { studied: true }), params());
      expect(response.status).toBe(422);
      expect(await response.json()).toEqual({ error: detail });
    },
  );

  // Red when: the confirm flag is dropped or forced, or the card count is lost.
  it("US-01 AC5: PUT textbook sends confirm only as given and passes 409 textbook_has_cards with the count", async () => {
    const calls = fakeCoreApi(() => refusal(409, { detail: "textbook_has_cards", cards: 12 }));
    const response = await putTextbook(send("PUT", `/api/subjects/${ID}/textbook`, { document_id: DOC }), params());
    expect(calls[0].body).toEqual({ document_id: DOC, confirm: false });
    expect(response.status).toBe(409);
    expect(await response.json()).toEqual({ error: "textbook_has_cards", cards: 12 });
    const again = fakeCoreApi(() => Response.json({ sections: [] }));
    await putTextbook(send("PUT", `/api/subjects/${ID}/textbook`, { document_id: DOC, confirm: true }), params());
    expect(again[0].body).toEqual({ document_id: DOC, confirm: true });
  });

  it("US-01 AC5: PUT textbook refuses a document id that is not a UUID", async () => {
    const calls = fakeCoreApi(() => Response.json({}));
    const response = await putTextbook(send("PUT", "/x", { document_id: "../x" }), params());
    expect(response.status).toBe(400);
    expect(calls).toHaveLength(0);
  });

  it("US-01 AC4: PATCH document passes a role on; an unknown role is refused; textbook_exists is kept", async () => {
    const calls = fakeCoreApi(() => refusal(409, { detail: "textbook_exists" }));
    const bad = await patchDocument(send("PATCH", "/x", { role: "boss" }), params());
    expect(bad.status).toBe(400);
    const response = await patchDocument(send("PATCH", "/x", { role: "textbook" }), params());
    expect(calls[0].path).toBe(`/v1/documents/${ID}`);
    expect(calls[0].body).toEqual({ role: "textbook" });
    expect(response.status).toBe(409);
    expect(await response.json()).toEqual({ error: "textbook_exists" });
  });

  it("US-01 AC7: PATCH document passes a short name; short_name_taken is kept", async () => {
    fakeCoreApi(() => refusal(409, { detail: "short_name_taken" }));
    const response = await patchDocument(send("PATCH", "/x", { short_name: "Slide" }), params());
    expect(await response.json()).toEqual({ error: "short_name_taken" });
  });

  it("US-13 AC1: GET outline and GET document read for the signed-in user; a refused origin is only for writes", async () => {
    const calls = fakeCoreApi(() => Response.json({ ok: 1 }));
    const outline = await readOutline(send("GET", "/x", undefined), params());
    const doc = await readDocument(send("GET", "/x", undefined), params());
    expect([outline.status, doc.status]).toEqual([200, 200]);
    expect(calls.map((c) => c.path)).toEqual([`/v1/subjects/${ID}/outline`, `/v1/documents/${ID}`]);
    const foreign = await patchSection(
      browserPost("/x", { studied: true }, { ...SIGNED_IN, method: "PATCH", origin: "https://evil.example" }),
      params(),
    );
    expect(foreign.status).toBe(403);
  });
});
