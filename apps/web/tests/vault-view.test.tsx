import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { VaultView } from "@/components/vault/vault-view";

const s = (id: string, name: string, sessions: number, cards: number) => ({ id, name, sessions, cards });

describe("VaultView subjects", () => {
  it("draws a grid of cards, no letter marks, the card count at display size", () => {
    const html = renderToStaticMarkup(<VaultView view={{ level: "subjects", subjects: [s("a", "Mạng máy tính", 6, 41)] }} />);
    expect(html).toContain("data-vault-subjects");
    expect(html).toMatch(/min-\[1100px\]:col-span-8/);
    expect(html).toMatch(/text-display[^>]*>41</);
    expect(html).toContain("6 buổi học");
    // UI-A: one display-size number (the whole vault); the tile's own count is smaller.
    expect(html).toMatch(/data-vault-total/);
    expect(html).toContain('href="/graph"');
    expect(html).toMatch(/text-title[^>]*data-vault-cards/);
    expect(html).not.toMatch(/tabular-nums text-ink-soft">M</);
  });
});
