import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { VaultView, withoutEmptyTwins } from "@/components/vault/vault-view";

const s = (id: string, name: string, sessions: number, cards: number) => ({ id, name, sessions, cards });

// UI-A: Kho kiến thức lists each subject once, as a card with the card count as its big number.
describe("withoutEmptyTwins", () => {
  it("hides an empty subject when a same-named one has content", () => {
    const out = withoutEmptyTwins([s("a", "Mạng máy tính", 0, 0), s("b", "Mạng máy tính", 1, 4), s("c", "Xác suất", 0, 0)]);
    expect(out.map((x) => x.id)).toEqual(["b", "c"]);
  });
  it("keeps one when every twin is empty, and never merges different names", () => {
    expect(withoutEmptyTwins([s("a", "Toán", 0, 0), s("b", "Toán", 0, 0)]).map((x) => x.id)).toEqual(["a"]);
    expect(withoutEmptyTwins([s("a", "Toán", 1, 1), s("b", "Toán", 2, 2)]).map((x) => x.id)).toEqual(["a", "b"]);
  });
});

describe("VaultView subjects", () => {
  it("draws a grid of cards, no letter marks, the card count at display size", () => {
    const html = renderToStaticMarkup(<VaultView view={{ level: "subjects", subjects: [s("a", "Mạng máy tính", 6, 41)] }} />);
    expect(html).toContain("data-vault-subjects");
    expect(html).toMatch(/min-\[1100px\]:grid-cols-3/);
    expect(html).toMatch(/text-display[^>]*>41</);
    expect(html).toContain("6 buổi học");
    expect(html).not.toMatch(/tabular-nums text-ink-soft">M</);
  });
});
