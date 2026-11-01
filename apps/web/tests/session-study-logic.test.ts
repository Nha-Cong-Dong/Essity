// T7.12a (US-02 AC2-AC4, AC6, AC8; DESIGN.md §6.7): the pure logic of the study-session screen:
// @ mentions in the description, the draft list, and the round state with its focus rule.
import { describe, expect, it } from "vitest";

import { DOCS } from "@/lib/fixtures/session-study";
import { draftsReducer, type Draft, savableCount } from "@/lib/session-study/drafts";
import { activeMention, applyMention, filterDocs, reconcileMentions } from "@/lib/session-study/mention";
import { initialRound, roundReducer } from "@/lib/session-study/round";

const draft = (id: string, extra: Partial<Draft> = {}): Draft => ({
  id,
  title: `Thẻ ${id}`,
  summary: `Ý ${id}`,
  section: "3.2",
  anchors: [{ id: `a-${id}`, kind: "document", label: "Giáo trình · tr. 47", quote: `Trích ${id}` }],
  origin: "ai",
  status: "draft",
  version: 1,
  conflict: null,
  source: "both",
  ...extra,
});

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
    expect(reconcileMentions("học @Giáo trình ", "học @Giáo trình mục 3.2", m)).toEqual({ mentions: m, removed: [] });
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

describe("draftsReducer (US-02 AC6, AC8, ADR-0028)", () => {
  const start = [draft("1"), draft("2"), draft("3")];

  // Red when: the user's edit is lost, or an edited card is not marked as the user's own.
  it("edit keeps the typed text and marks the card as edited", () => {
    const next = draftsReducer(start, { type: "edit", id: "2", patch: { summary: "Của tôi" } });
    expect(next[1]).toMatchObject({ summary: "Của tôi", origin: "user" });
  });

  // Red when: discarding deletes the card (it must be retired and come back with undo).
  it("discard retires, undo brings it back in place", () => {
    const gone = draftsReducer(start, { type: "discard", id: "2" });
    expect(gone[1].status).toBe("retired");
    expect(savableCount(gone)).toBe(2);
    expect(draftsReducer(gone, { type: "undo", id: "2" })[1].status).toBe("draft");
  });

  // Red when: merging drops an anchor or keeps both cards.
  it("merge folds the source into the target and adds up the anchors", () => {
    const next = draftsReducer(start, { type: "merge", sourceId: "1", targetId: "3" });
    expect(next.map((d) => d.id)).toEqual(["2", "3"]);
    expect(next[1].anchors).toHaveLength(2);
    expect(next[1].summary).toContain("Ý 3");
    expect(next[1].summary).toContain("Ý 1");
  });

  it("split turns one card into two, in place", () => {
    const next = draftsReducer(start, {
      type: "split",
      id: "2",
      parts: [
        { id: "2a", title: "A", summary: "a" },
        { id: "2b", title: "B", summary: "b" },
      ],
    });
    expect(next.map((d) => d.id)).toEqual(["1", "2a", "2b", "3"]);
    expect(next[1].anchors).toEqual(start[1].anchors);
  });

  // Red when: a late AI card is put before the user's own cards or rewrites an existing card.
  it("late AI cards go after the existing ones and change nothing else", () => {
    const mine = draftsReducer(start, { type: "add", id: "u1" });
    const next = draftsReducer(mine, { type: "append-ai", drafts: [draft("9")] });
    expect(next.map((d) => d.id)).toEqual(["1", "2", "3", "u1", "9"]);
    expect(next.slice(0, 4)).toEqual(mine);
  });

  // Red when: a 409 drops what the user typed, or reload leaves the conflict flag on.
  it("conflict keeps the user's text; reload clears the flag and takes the server's card", () => {
    const hit = draftsReducer(start, { type: "conflict", id: "1", mine: "chữ đang gõ" });
    expect(hit[0].conflict).toEqual({ mine: "chữ đang gõ" });
    const back = draftsReducer(hit, { type: "reload", draft: draft("1", { summary: "bản mới", version: 2 }) });
    expect(back[0]).toMatchObject({ summary: "bản mới", conflict: null, version: 2 });
  });

  // Red when: an empty new card counts toward "Sẽ lưu N thẻ".
  it("an empty added card is not saved", () => {
    const next = draftsReducer([], { type: "add", id: "u1" });
    expect(savableCount(next)).toBe(0);
    expect(savableCount(draftsReducer(next, { type: "edit", id: "u1", patch: { title: "Ý của tôi" } }))).toBe(1);
  });
});

describe("roundReducer (US-02 AC4 scope refused, AC9-AC11 processing, AC14 Học tiếp; DESIGN.md §6.7 vùng 1-5; review C5: focus only follows the user's own action)", () => {
  // Red when: processing finishing in the background asks for focus (it would steal the caret
  // from a card being edited).
  it("a background change never asks for focus; the user's Gửi, Lưu and Học tiếp do", () => {
    let s = roundReducer(initialRound, { type: "send" });
    expect(s).toMatchObject({ phase: "processing", focus: "processing" });
    s = roundReducer(s, { type: "drafts-ready", count: 6 });
    expect(s).toMatchObject({ phase: "review", focus: null, announce: "Đã tách 6 thẻ nháp." });
    s = roundReducer(s, { type: "save-ok" });
    expect(s).toMatchObject({ phase: "saved", focus: "saved" });
    s = roundReducer(s, { type: "continue" });
    expect(s).toMatchObject({ phase: "compose", round: 2, focus: "compose" });
  });

  // Red when: a partly read submission is stuck in the processing area instead of reaching the cards.
  it("a partly failed read goes on to review with the note; a whole failure stays in processing", () => {
    const base = roundReducer(initialRound, { type: "send" });
    expect(roundReducer(base, { type: "partial", count: 4 })).toMatchObject({ phase: "review", partialNote: true });
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

  // Red when: Thử lại does not go back to waiting, or a save error loses the review.
  it("retry waits again; a failed save stays in review", () => {
    const failed = roundReducer(roundReducer(initialRound, { type: "send" }), { type: "failed" });
    expect(roundReducer(failed, { type: "retry" })).toMatchObject({ phase: "processing", submission: "queued" });
    const review = roundReducer(roundReducer(initialRound, { type: "send" }), { type: "drafts-ready", count: 2 });
    expect(roundReducer(review, { type: "save-error" })).toMatchObject({ phase: "review", saveError: true });
  });
});

describe("drafts reducer, answers from core-api (T7.12)", () => {
  // US-02b AC6, AC9. Red when: a card added here keeps its local id (Save would send a stranger)
  // or the version after an edit is not kept (the next edit would be a 409).
  it("synced gives a card its real id and version, keeping what was typed", () => {
    const list = [draft("new-1", { summary: "đang gõ" })];
    expect(draftsReducer(list, { type: "synced", id: "new-1", to: "u9", version: 4 })).toMatchObject([
      { id: "u9", version: 4, summary: "đang gõ" },
    ]);
  });

  // US-02b AC8. Red when: the merged card lands at the end instead of where the first card was.
  it("replace puts core-api's cards where the first replaced card stood", () => {
    const list = [draft("a"), draft("b"), draft("c"), draft("d")];
    const out = draftsReducer(list, { type: "replace", ids: ["b", "d"], drafts: [draft("m")] });
    expect(out.map((d) => d.id)).toEqual(["a", "m", "c"]);
    expect(draftsReducer(list, { type: "replace", ids: ["zz"], drafts: [draft("m")] })).toBe(list);
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
