// T7.12 (US-02 AC2-AC4, AC13; US-02b AC6-AC9): the browser's side of the study session: core-api's
// cards as the screen's cards, and each action as one call to web's routes.
import { describe, expect, it, vi } from "vitest";

import { createSessionApi, readStatus, toDraft } from "@/lib/session-study/api";
import type { DocRef } from "@/lib/session-study/mention";

const SID = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const DOC = "5a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d";
const DOCS: DocRef[] = [{ id: DOC, name: "Giáo trình", role: "Giáo trình chính" }];

const core = (patch: Record<string, unknown> = {}) => ({
  id: "u1",
  session_id: SID,
  title: "Cửa sổ trượt",
  content: "Bên gửi giữ rwnd.",
  kind: "concept",
  status: "draft",
  version: 2,
  section_ids: [],
  anchors: [
    { id: "a1", source: "document", document_id: DOC, page_no: 52, start: 0, end: 5, quote_text: "rwnd" },
    { id: "a2", source: "notes", document_id: null, page_no: null, start: null, end: null, quote_text: "vở" },
  ],
  revisions: [{ rev: 0, origin: "ai", content: {} }],
  ...patch,
});

function fakeFetch(reply: (url: string, init: RequestInit) => Response) {
  const calls: { url: string; init: RequestInit; body: unknown }[] = [];
  const fn = vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url, init, body: init.body ? JSON.parse(String(init.body)) : undefined });
    return reply(url, init);
  });
  return { fn: fn as unknown as typeof fetch, calls };
}

describe("toDraft", () => {
  // US-02 AC5. Red when: where the card was seen (notebook, textbook, both) is lost, or an anchor
  // loses its document name or page.
  it("maps a card, its anchors and where it was seen", () => {
    const draft = toDraft(core(), DOCS);
    expect(draft).toMatchObject({ id: "u1", title: "Cửa sổ trượt", summary: "Bên gửi giữ rwnd.", version: 2, status: "draft", origin: "ai", source: "both", conflict: null });
    expect(draft.anchors.map((a) => a.label)).toEqual(["Giáo trình · tr. 52", "Vở ghi"]);
    expect(toDraft(core({ anchors: [] }), DOCS).source).toBe("both");
    expect(toDraft(core({ anchors: [core().anchors[1]] }), DOCS).source).toBe("notes");
    expect(toDraft(core({ anchors: [core().anchors[0]] }), DOCS).source).toBe("document");
  });

  // US-02b AC7. Red when: a card the learner edited still says "ai".
  it("marks a card the learner wrote as theirs", () => {
    const edited = core({ revisions: [{ rev: 0, origin: "ai", content: {} }, { rev: 1, origin: "user", content: {} }] });
    expect(toDraft(edited, DOCS).origin).toBe("user");
    expect(toDraft(core({ status: "retired" }), DOCS).status).toBe("retired");
  });
});

describe("readStatus", () => {
  // US-02 AC11. Red when: a status core-api sends has no phase on the screen.
  it.each([
    ["queued", "queued"],
    ["processing", "processing"],
    ["pending_ai", "pending_ai"],
    ["failed", "failed"],
    ["done", "done"],
    [null, "none"],
    ["something-new", "processing"],
  ])("%s is %s", (status, phase) => {
    expect(readStatus(status)).toBe(phase);
  });
});

describe("createSessionApi", () => {
  it("submits the sentence with its mentions and answers the status", async () => {
    const { fn, calls } = fakeFetch(() => Response.json({ submission_id: "s", session_id: SID, status: "queued", mentions: [] }, { status: 201 }));
    const api = createSessionApi(SID, DOCS, fn);
    const result = await api.submit("học @Giáo trình mục 3.2", [{ docId: DOC, name: "Giáo trình", start: 4, end: 14 }]);
    expect(calls[0].url).toBe("/api/submissions");
    expect(calls[0].body).toEqual({ session_id: SID, description: "học @Giáo trình mục 3.2", mentions: [{ document_id: DOC, start: 4, end: 14 }] });
    expect(result).toEqual({ ok: true, data: { status: "queued" } });
  });

  // US-02 AC4. Red when: the refused mention's document is not found from its index.
  it("names the document of a refused mention", async () => {
    const { fn } = fakeFetch(() => Response.json({ error: "scope_not_found", mention: 1 }, { status: 422 }));
    const api = createSessionApi(SID, DOCS, fn);
    const mentions = [
      { docId: "x", name: "A", start: 0, end: 2 },
      { docId: DOC, name: "Giáo trình", start: 5, end: 15 },
    ];
    expect(await api.submit("x", mentions)).toEqual({ ok: false, status: 422, error: "scope_not_found", docId: DOC });
  });

  it("loads the cards and the status, keeping only drafts and discarded ones", async () => {
    const { fn, calls } = fakeFetch(() => Response.json({ drafts: [core(), core({ id: "u2", status: "canonical" }), core({ id: "u3", status: "retired" })], submission_status: "done" }));
    const result = await createSessionApi(SID, DOCS, fn).load();
    expect(calls[0].url).toBe(`/api/sessions/${SID}/drafts`);
    expect(result.ok && result.data.phase).toBe("done");
    expect(result.ok && result.data.drafts.map((d) => d.id)).toEqual(["u1", "u3"]);
  });

  // US-02b AC6, AC7. Red when: the version the learner saw is not sent, or a 409 is not told
  // apart from a failure.
  it("edits with the version and tells a 409 from a failure", async () => {
    const { fn, calls } = fakeFetch(() => Response.json(core({ version: 3, title: "T2" })));
    const api = createSessionApi(SID, DOCS, fn);
    const ok = await api.edit("u1", 2, { title: "T2" });
    expect(calls[0]).toMatchObject({ url: "/api/drafts/u1", body: { version: 2, title: "T2" } });
    expect(calls[0].init.method).toBe("PATCH");
    expect(ok.ok && ok.data.version).toBe(3);
    const stale = createSessionApi(SID, DOCS, fakeFetch(() => Response.json({ error: "unit_changed_elsewhere" }, { status: 409 })).fn);
    expect(await stale.edit("u1", 1, { title: "x" })).toMatchObject({ ok: false, status: 409, error: "unit_changed_elsewhere" });
    const down = createSessionApi(SID, DOCS, fakeFetch(() => { throw new Error("offline"); }).fn);
    expect(await down.edit("u1", 1, { title: "x" })).toMatchObject({ ok: false, status: 0, error: "network" });
  });

  it("discards, undoes, adds, merges, splits and saves through the routes", async () => {
    const { fn, calls } = fakeFetch((url) => (url.endsWith("/save") ? Response.json({ saved: ["u1"] }) : url.endsWith("/split") ? Response.json({ drafts: [core({ id: "a" }), core({ id: "b" })], submission_status: null }) : Response.json(core())));
    const api = createSessionApi(SID, DOCS, fn);
    await api.discard("u1");
    await api.undo("u1");
    await api.add("T", "C");
    await api.merge(["u1", "u2"]);
    const parts = await api.split("u1", 2, [{ title: "A", content: "a" }, { title: "B", content: "b" }]);
    const saved = await api.save([{ id: "u1", version: 2 }]);
    expect(calls.map((c) => `${c.init.method ?? "GET"} ${c.url.replace(SID, "SID")}`)).toEqual([
      "DELETE /api/drafts/u1",
      "POST /api/drafts/u1/undo",
      "POST /api/sessions/SID/drafts",
      "POST /api/sessions/SID/drafts/merge",
      "POST /api/drafts/u1/split",
      "POST /api/sessions/SID/drafts/save",
    ]);
    expect(calls[4].body).toEqual({ version: 2, parts: [{ title: "A", content: "a", anchor_ids: [] }, { title: "B", content: "b", anchor_ids: [] }] });
    expect(calls[5].body).toEqual({ units: [{ unit_id: "u1", version: 2 }] });
    expect(parts.ok && parts.data.map((d) => d.id)).toEqual(["a", "b"]);
    expect(saved).toEqual({ ok: true, data: ["u1"] });
  });
});
