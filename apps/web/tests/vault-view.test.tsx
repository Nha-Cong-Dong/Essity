import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { VaultView } from "@/components/vault/vault-view";

const s = (id: string, name: string, sessions: number, cards: number) => ({ id, name, sessions, cards });

describe("VaultView subjects", () => {
  it("opens with the plum field (the whole vault's number), then one sheet of full-row links", () => {
    const html = renderToStaticMarkup(<VaultView view={{ level: "subjects", subjects: [s("a", "Mạng máy tính", 6, 41)] }} />);
    expect(html).toContain("data-vault-subjects");
    expect(html).toContain('data-tier="field"');
    expect(html).toMatch(/text-display[^>]*data-vault-total[^>]*>41</);
    expect(html).toContain("6 buổi học");
    expect(html).toContain('href="/kho-kien-thuc?subject=a"');
    // The graph block is gone from the Kho (design-v4): no "Đồ thị tri thức" and no link to it.
    expect(html).not.toContain("Đồ thị tri thức");
    expect(html).not.toContain('href="/graph"');
  });
});

describe("VaultView headings", () => {
  it("each level has exactly one h1", () => {
    const sessions = renderToStaticMarkup(<VaultView view={{ level: "sessions", sessions: [] }} subjectId="a" />);
    expect(sessions.match(/<h1/g)).toHaveLength(1);
    const cards = renderToStaticMarkup(<VaultView view={{ level: "cards", title: "Buổi", cards: [] }} subjectId="a" />);
    expect(cards.match(/<h1/g)).toHaveLength(1);
  });

  it("deep levels go back with the shared BackLink wording", () => {
    const sessions = renderToStaticMarkup(<VaultView view={{ level: "sessions", sessions: [] }} subjectId="a" />);
    expect(sessions).toMatch(/href="\/kho-kien-thuc"[^>]*>[\s\S]*Quay lại/);
    const cards = renderToStaticMarkup(<VaultView view={{ level: "cards", title: "Buổi", cards: [] }} subjectId="a" />);
    expect(cards).toContain('href="/kho-kien-thuc?subject=a"');
    expect(cards).toContain("Quay lại");
  });

  it("a session row shows its day as a tile and links the whole row", () => {
    const html = renderToStaticMarkup(
      <VaultView
        view={{ level: "sessions", subjectName: "Xác suất thống kê", sessions: [{ id: "x", title: "Quy tắc đếm", studied_on: "03/11/2026", cards: 6 }] }}
        subjectId="a"
      />,
    );
    expect(html).toContain("Xác suất thống kê");
    expect(html).toContain("Th11");
    expect(html).toMatch(/<a href="\/kho-kien-thuc\?subject=a&(amp;)?session=x"/);
    expect(html).toContain("6 thẻ");
  });
});
