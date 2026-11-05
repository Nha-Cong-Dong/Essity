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

describe("VaultView headings", () => {
  it("each level has exactly one h1 (the graph's title is an h2)", () => {
    const graphs = [{ id: "a", name: "Xác suất thống kê", data: { sections: [], cards: [], edges: [] } }];
    const sessions = renderToStaticMarkup(<VaultView view={{ level: "sessions", sessions: [], graphs }} subjectId="a" />);
    expect(sessions.match(/<h1/g)).toHaveLength(1);
    const cards = renderToStaticMarkup(<VaultView view={{ level: "cards", title: "Buổi", cards: [] }} subjectId="a" />);
    expect(cards.match(/<h1/g)).toHaveLength(1);
  });
});
