// T7.12a (US-02 AC2-AC4, AC6, AC8; DESIGN.md §6.7): the pure logic of the study-session screen:
// @ mentions in the description, and the round state with its focus rule.
import { describe, expect, it } from "vitest";

import { DOCS } from "@/lib/fixtures/session-study";
import { activeMention, applyMention, filterDocs, reconcileMentions } from "@/lib/session-study/mention";
import { initialRound, roundFromResult, roundReducer } from "@/lib/session-study/round";

describe("activeMention (US-02 AC2)", () => {
  // Red when: typing @ in the middle of a word (an email) opens the menu, or the query is wrong.
  it("opens on @ at the start or after a space, not inside a word", () => {
    expect(activeMention("học @Giáo", 9, [])).toEqual({ at: 4, query: "Giáo" });
    expect(activeMention("@", 1, [])).toEqual({ at: 0, query: "" });
    expect(activeMention("ban@x", 5, [])).toBeNull();
  });

  // Red when: a name with a space ("slide c3") closes the menu at the space.
  it("keeps the query across spaces on one line", () => {
    expect(activeMention("xem @slide c", 12, [])).toEqual({ at: 4, query: "slide c" });
    expect(activeMention("xem @slide\nc", 12, [])).toBeNull();
  });

  // Red when: the chosen mention reopens the menu as soon as the caret sits after it.
  it("ignores an @ that already starts a chosen mention", () => {
    const text = "học @Giáo trình ";
    expect(activeMention(text, text.length, [{ docId: "d1", name: "Giáo trình", start: 4, end: 15 }])).toBeNull();
  });
});

describe("filterDocs (US-02 AC2)", () => {
  // Red when: the filter is case- or accent-sensitive, or the menu grows past six rows.
  it("matches without case or accents and shows at most 6", () => {
    expect(filterDocs(DOCS, "giao").map((doc) => doc.name)).toContain("Giáo trình");
    expect(filterDocs(DOCS, "SLIDE").length).toBeGreaterThan(0);
    expect(filterDocs(DOCS, "").length).toBeLessThanOrEqual(6);
    expect(filterDocs(DOCS, "zzzz")).toEqual([]);
  });
});

describe("applyMention and reconcileMentions (US-02 AC2, AC3: a reference is exact, never guessed)", () => {
  const doc = { id: "d1", name: "Giáo trình", role: "Giáo trình" };

  it("replaces @query by @name and records the range by document id", () => {
    const result = applyMention("học @Gi", 4, 7, doc, []);
    expect(result.text).toBe("học @Giáo trình ");
    expect(result.caret).toBe(result.text.length);
    expect(result.mentions).toEqual([{ docId: "d1", name: "Giáo trình", start: 4, end: 15 }]);
  });

  // Red when: typing after the chip (the scope words) drops the chip, or typing before it leaves it
  // pointing at the wrong characters.
  it("keeps a mention when text is added after it and shifts it when text is added before", () => {
    const m = [{ docId: "d1", name: "Giáo trình", start: 4, end: 15 }];
    expect(reconcileMentions("học @Giáo trình ", "học @Giáo trình phần 3.2", m)).toEqual({ mentions: m, removed: [] });
    const shifted = reconcileMentions("học @Giáo trình ", "tối nay học @Giáo trình ", m);
    expect(shifted.mentions[0]).toMatchObject({ start: 12, end: 23 });
  });

  // Red when: editing inside the name leaves an orphan chip that no longer names the document.
  it("removes a mention whose characters were edited and reports it", () => {
    const m = [{ docId: "d1", name: "Giáo trình", start: 4, end: 15 }];
    const result = reconcileMentions("học @Giáo trình ", "học @Giáo trXnh ", m);
    expect(result.mentions).toEqual([]);
    expect(result.removed).toEqual(m);
  });
});

describe("roundReducer (US-02 AC4 scope refused, AC9-AC11 processing; CARDS-V3: cards go straight to the Kho; review C5: focus only follows the user's own action)", () => {
  // Red when: the result arriving in the background asks for focus (it would steal the caret).
  it("a background change never asks for focus; the user's Gửi and Học tiếp do", () => {
    let s = roundReducer(initialRound, { type: "send" });
    expect(s).toMatchObject({ phase: "processing", focus: "processing" });
    s = roundReducer(s, { type: "done", result: { cards: 6, title: "TCP", notice: null } });
    expect(s).toMatchObject({ phase: "done", focus: null, result: { cards: 6, title: "TCP" }, announce: "Đã thêm 6 thẻ vào Kho." });
    s = roundReducer(s, { type: "continue" });
    expect(s).toMatchObject({ phase: "compose", round: 2, focus: "compose", result: null });
  });

  // Red when: a done read with no card is silent (no announce) or is told as "0 thẻ đã thêm".
  it("a done read with no card says so", () => {
    const base = roundReducer(initialRound, { type: "send" });
    const s = roundReducer(base, { type: "done", result: { cards: 0, title: null, notice: "no_content_found" } });
    expect(s).toMatchObject({ phase: "done", result: { cards: 0 }, announce: "Chưa tìm thấy nội dung để làm thẻ." });
  });

  // Red when: a whole failure or the AI limit leaves the processing area.
  it("a failure and the AI limit stay in processing", () => {
    const base = roundReducer(initialRound, { type: "send" });
    expect(roundReducer(base, { type: "failed" })).toMatchObject({ phase: "processing", submission: "failed" });
    expect(roundReducer(base, { type: "pending-ai" })).toMatchObject({ phase: "processing", submission: "pending_ai" });
  });

  // Red when: a refused @ scope sends the user to processing; it must stay on the form (review C2).
  it("a refused scope returns to compose with the mention to fix", () => {
    const base = roundReducer(initialRound, { type: "send" });
    expect(roundReducer(base, { type: "scope-rejected", docId: "d1" })).toMatchObject({
      phase: "compose",
      rejectedDoc: "d1",
      focus: "compose",
    });
  });

  // Red when: Thử lại does not go back to waiting.
  it("retry waits again", () => {
    const failed = roundReducer(roundReducer(initialRound, { type: "send" }), { type: "failed" });
    expect(roundReducer(failed, { type: "retry" })).toMatchObject({ phase: "processing", submission: "queued" });
  });
});

describe("round reducer, a send that went wrong (T7.12)", () => {
  // US-02 AC11. Red when: after a failed send the learner stays on "processing" (no way back).
  it("back returns to the form and moves the focus there", () => {
    const sent = roundReducer(initialRound, { type: "send" });
    expect(sent.phase).toBe("processing");
    expect(roundReducer(sent, { type: "back" })).toMatchObject({ phase: "compose", submission: null, focus: "compose" });
  });
});

describe("roundFromResult (CARDS-V3: a reopened session shows where it truly is)", () => {
  // Red when: a reopened finished session shows the form again, or loses its 0-card notice.
  it("done opens the result, with or without cards", () => {
    expect(roundFromResult("done", { cards: 3, title: "TCP", notice: null })).toMatchObject({ phase: "done", result: { cards: 3, title: "TCP" } });
    expect(roundFromResult("done", { cards: 0, title: null, notice: "no_content_found" })).toMatchObject({ phase: "done", result: { cards: 0 } });
  });

  // Red when: a reading still running opens the form (a second send) or a failure opens the form.
  it("a read in progress or failed opens the processing area; nothing handed in opens the form", () => {
    for (const status of ["queued", "processing", "pending_ai", "failed"] as const) {
      expect(roundFromResult(status, null)).toMatchObject({ phase: "processing", submission: status });
    }
    expect(roundFromResult("none", null)).toEqual(initialRound);
  });
});
