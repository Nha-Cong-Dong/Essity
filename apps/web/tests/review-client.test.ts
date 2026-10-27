// T2.15 (plan step 9): the answer screen's calls to web's routes. Every failure comes back as a
// code, never thrown; signed out goes to /login.
import { afterEach, describe, expect, it, vi } from "vitest";

const go = vi.fn();
vi.mock("@/lib/navigate", () => ({ go: (path: string) => go(path) }));

const { reviewApi } = await import("@/lib/review-client");
const ID = "6b1c2d3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e";
const ANSWER = { answer_text: "TCP tin cậy", dont_remember: false };

function reply(response: Response | Error) {
  const fetchMock = vi.fn(async () => {
    if (response instanceof Error) throw response;
    return response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("reviewApi (T2.15)", () => {
  afterEach(() => go.mockReset());

  // Red when: a saved draft (204, no body) reads as "unavailable", so the box never says saved.
  it("a draft saved with 204 is ok", async () => {
    reply(new Response(null, { status: 204 }));
    expect(await reviewApi.saveDraft(ID, ANSWER)).toEqual({ ok: true, data: null });
  });

  it("sends the answer as JSON to the attempt's route", async () => {
    const fetchMock = reply(Response.json({ status: "submitted" }));
    await reviewApi.submit(ID, ANSWER);
    expect(fetchMock).toHaveBeenCalledWith(`/api/attempts/${ID}/submit`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(ANSWER),
    });
  });

  it("a refusal comes back as its code", async () => {
    reply(Response.json({ error: "session_ended" }, { status: 409 }));
    expect(await reviewApi.saveDraft(ID, ANSWER)).toEqual({ ok: false, error: "session_ended" });
  });

  it("no network is offline", async () => {
    reply(new TypeError("fetch failed"));
    expect(await reviewApi.current(ID)).toEqual({ ok: false, error: "offline" });
  });

  it("signed out goes to /login", async () => {
    reply(Response.json({ error: "signed_out" }, { status: 401 }));
    expect(await reviewApi.stop(ID)).toEqual({ ok: false, error: "signed_out" });
    expect(go).toHaveBeenCalledWith("/login");
  });
});
