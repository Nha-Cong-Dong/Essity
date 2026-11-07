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

describe("VaultView subjects hero (SCREENS-V4-B)", () => {
  const recent = (title: string, studied_on: string) => ({ title, studied_on });
  const subjects = [
    { ...s("a", "Xác suất", 2, 31), recent: [recent("Hoán vị", "2026-11-07"), recent("Quy tắc cộng", "2026-11-03")] },
    { ...s("b", "Mạng", 1, 16), recent: [recent("ARP", "2026-11-05")] },
  ];

  // Red when: the hero has no "Mới thêm" list, or it is not newest-first across subjects, or the header mascot stays.
  it("lists the newest sessions in the hero, newest first, and draws no header mascot", () => {
    const html = renderToStaticMarkup(<VaultView view={{ level: "subjects", subjects }} />);
    expect(html).toContain("Mới thêm");
    const hero = html.slice(html.indexOf('data-tier="field"'), html.indexOf("data-vault-subjects"));
    expect(hero.indexOf("Hoán vị")).toBeGreaterThan(-1);
    expect(hero.indexOf("Hoán vị")).toBeLessThan(hero.indexOf("ARP"));
    expect(hero.indexOf("ARP")).toBeLessThan(hero.indexOf("Quy tắc cộng"));
    expect(html).not.toContain("data-mascot");
  });

  // Red when: a subject row lacks the chips of its sessions.
  it("a subject row carries chips of its recent sessions", () => {
    const html = renderToStaticMarkup(<VaultView view={{ level: "subjects", subjects }} />);
    const rows = html.slice(html.indexOf("data-vault-subjects"));
    expect(rows).toContain("Quy tắc cộng");
  });

  // Red when: a vault without recent data still draws an empty "Mới thêm".
  it("no recent data: no 'Mới thêm'", () => {
    const html = renderToStaticMarkup(<VaultView view={{ level: "subjects", subjects: [s("a", "X", 1, 2)] }} />);
    expect(html).not.toContain("Mới thêm");
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
