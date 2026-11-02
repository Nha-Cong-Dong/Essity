// T7.13 (US-15 AC6): the browser's call for "Gợi ý cho hôm nay".
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchSubjectSuggestion } from "@/lib/suggestion-client";

const ID = "0b8f1d2e-0000-4000-8000-000000000001";
const answer = (r: Response | Error) =>
  vi.stubGlobal("fetch", vi.fn(async () => { if (r instanceof Error) throw r; return r; }));

describe("fetchSubjectSuggestion", () => {
  afterEach(() => vi.unstubAllGlobals());

  // Red when: the call goes to another route or the answer is not mapped.
  it("asks this subject's route and maps the suggestion", async () => {
    answer(Response.json({
      today: "2026-11-02",
      suggestion: { subject_id: ID, subject_name: "M", kind: "free_session", section_id: null, section_title: null, partial: false, remaining: null, unit: null, reason: "r", pace: { remaining_leaves: 0, remaining_weight: 0, unit: null, days_left: null, text: "" } },
    }));
    expect(await fetchSubjectSuggestion(ID)).toEqual({ kind: "no_textbook" });
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe(`/api/subjects/${ID}/suggestion`);
  });

  // Red when: an error status or a wrong body is read as a suggestion (the block would hang).
  it.each([[Response.json({ error: "unavailable" }, { status: 502 })], [Response.json({})], [new Error("net")]])(
    "throws on anything that is not a suggestion",
    async (response) => {
      answer(response);
      await expect(fetchSubjectSuggestion(ID)).rejects.toThrow();
    },
  );
});
