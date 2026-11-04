// T7.12 (US-02 AC2-AC4, AC13; CARDS-V3): the browser's side of the study session: each action as one
// call to web's routes, and where the handed-in session stands.
import { describe, expect, it, vi } from "vitest";

import { createSessionApi, readStatus } from "@/lib/session-study/api";
import type { DocRef } from "@/lib/session-study/mention";

const SID = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const DOC = "5a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d";
const DOCS: DocRef[] = [{ id: DOC, name: "Giáo trình", role: "Giáo trình chính" }];

function fakeFetch(reply: (url: string, init: RequestInit) => Response) {
  const calls: { url: string; init: RequestInit; body: unknown }[] = [];
  const fn = vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url, init, body: init.body ? JSON.parse(String(init.body)) : undefined });
    return reply(url, init);
  });
  return { fn: fn as unknown as typeof fetch, calls };
}

describe("readStatus", () => {
  // US-02 AC11, AC15. Red when: a status core-api sends has no phase on the screen.
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
    const result = await api.submit("học @Giáo trình phần 3.2", [{ docId: DOC, name: "Giáo trình", start: 4, end: 14 }]);
    expect(calls[0].url).toBe("/api/submissions");
    expect(calls[0].body).toEqual({ session_id: SID, description: "học @Giáo trình phần 3.2", mentions: [{ document_id: DOC, start: 4, end: 14 }] });
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

  // CARDS-V3. Red when: the poll reads the old drafts route, or a status/notice from core-api is lost.
  it("reads where the session stands from the result route", async () => {
    const { fn, calls } = fakeFetch(() =>
      Response.json({ session_id: SID, submission_status: "done", title: "TCP flow control", cards: 5, notice: null }),
    );
    const result = await createSessionApi(SID, DOCS, fn).result();
    expect(calls[0].url).toBe(`/api/sessions/${SID}/result`);
    expect(result).toEqual({ ok: true, data: { phase: "done", title: "TCP flow control", cards: 5, notice: null } });
  });

  // CARDS-V3. Red when: a done session with no card loses its notice (the screen would be silent).
  it("keeps the notice of a done session with no card", async () => {
    const { fn } = fakeFetch(() => Response.json({ session_id: SID, submission_status: "done", title: null, cards: 0, notice: "no_content_found" }));
    const result = await createSessionApi(SID, DOCS, fn).result();
    expect(result).toEqual({ ok: true, data: { phase: "done", title: null, cards: 0, notice: "no_content_found" } });
  });

  it("answers a refusal or a dropped network as an error, never a throw", async () => {
    const down = createSessionApi(SID, DOCS, fakeFetch(() => { throw new Error("offline"); }).fn);
    expect(await down.result()).toMatchObject({ ok: false, status: 0, error: "network" });
    const gone = createSessionApi(SID, DOCS, fakeFetch(() => Response.json({ error: "session_not_found" }, { status: 404 })).fn);
    expect(await gone.result()).toMatchObject({ ok: false, status: 404, error: "session_not_found" });
  });
});
