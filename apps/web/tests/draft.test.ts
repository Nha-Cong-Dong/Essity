// T2.15 (plan step 8, 🟡14): the answer kept on this device while core-api cannot be reached, so
// a dropped connection or a closed tab loses nothing typed.
import { describe, expect, it } from "vitest";

import { clearAllDrafts, clearDraft, DRAFT_MAX_AGE_MS, pickDraft, readDraft, writeDraft } from "@/lib/draft";

const A = "6b1c2d3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e";
const B = "3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b";

function memory(): Storage {
  const items = new Map<string, string>();
  return {
    get length() {
      return items.size;
    },
    key: (n) => [...items.keys()][n] ?? null,
    getItem: (key) => items.get(key) ?? null,
    setItem: (key, value) => void items.set(key, value),
    removeItem: (key) => void items.delete(key),
    clear: () => items.clear(),
  };
}

const NOW = 1_800_000_000_000;

describe("lib/draft (T2.15)", () => {
  it("keeps a draft per attempt and gives it back", () => {
    const storage = memory();
    writeDraft(A, { text: "TCP\ntin cậy", dontRemember: false, synced: false }, { storage, now: NOW });
    expect(readDraft(A, { storage, now: NOW })).toEqual({
      text: "TCP\ntin cậy",
      dontRemember: false,
      synced: false,
      savedAt: NOW,
    });
    expect(readDraft(B, { storage, now: NOW })).toBeNull();
  });

  // Red when: text typed while the server could not be reached is replaced by the server's older
  // draft on reload.
  it("text the server never got wins over the server's draft", () => {
    const local = { text: "mới gõ", dontRemember: false, synced: false, savedAt: NOW };
    expect(pickDraft(local, { answer_text: "cũ", dont_remember: false })).toEqual({
      text: "mới gõ",
      dontRemember: false,
    });
  });

  // Red when: a draft saved on another device later is hidden by this device's old copy.
  it("once the server has it, the server's draft wins (another device may have written since)", () => {
    const local = { text: "cũ", dontRemember: false, synced: true, savedAt: NOW };
    expect(pickDraft(local, { answer_text: "từ máy khác", dont_remember: false })).toEqual({
      text: "từ máy khác",
      dontRemember: false,
    });
    expect(pickDraft(null, { answer_text: "s", dont_remember: true })).toEqual({ text: "s", dontRemember: true });
  });

  it("a draft older than its keeping time is dropped", () => {
    const storage = memory();
    writeDraft(A, { text: "x", dontRemember: false, synced: false }, { storage, now: NOW });
    expect(readDraft(A, { storage, now: NOW + DRAFT_MAX_AGE_MS + 1 })).toBeNull();
    expect(storage.length).toBe(0);
  });

  it("clearing one attempt leaves the others; signing out clears every draft and nothing else", () => {
    const storage = memory();
    storage.setItem("theme", "dark");
    writeDraft(A, { text: "a", dontRemember: false, synced: false }, { storage, now: NOW });
    writeDraft(B, { text: "b", dontRemember: false, synced: false }, { storage, now: NOW });
    clearDraft(A, { storage });
    expect(readDraft(A, { storage, now: NOW })).toBeNull();
    expect(readDraft(B, { storage, now: NOW })?.text).toBe("b");
    clearAllDrafts({ storage });
    expect(storage.length).toBe(1);
    expect(storage.getItem("theme")).toBe("dark");
  });

  it("a broken or foreign entry reads as no draft", () => {
    const storage = memory();
    storage.setItem(`essity:draft:${A}`, "{not json");
    expect(readDraft(A, { storage, now: NOW })).toBeNull();
    storage.setItem(`essity:draft:${A}`, JSON.stringify({ text: 7 }));
    expect(readDraft(A, { storage, now: NOW })).toBeNull();
  });

  // Private mode, storage full or blocked: typing must still work.
  it("a storage that throws is ignored", () => {
    const broken = {
      ...memory(),
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("full");
      },
    } as Storage;
    expect(() => writeDraft(A, { text: "x", dontRemember: false, synced: false }, { storage: broken })).not.toThrow();
    expect(readDraft(A, { storage: broken })).toBeNull();
  });
});
