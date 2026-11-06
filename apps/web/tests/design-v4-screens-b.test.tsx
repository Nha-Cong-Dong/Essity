// @vitest-environment jsdom
// V4-SCREENS-B: the session screen and the Kho in the v4 look. Red when: the end-of-session pop-up loses its
// plum band and mascot, the session has two "Kết thúc buổi học" buttons or no plum column, the cards of a
// session are not a horizontal band of white sheets on a plum stage, the Kho keeps the graph block, or a
// colour is hard-coded in these folders.
import { cleanup, render, screen } from "@testing-library/react";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { END_COPY, SessionEndDialog } from "@/components/session-study/session-end-dialog";
import { type SessionInitial, SessionScreen } from "@/components/session-study/session-screen";
import { CardList } from "@/components/vault/card-list";
import type { ApiResult, SessionApi } from "@/lib/session-study/api";
import { initialRound } from "@/lib/session-study/round";

const ok = <T,>(data: T): Promise<ApiResult<T>> => Promise.resolve({ ok: true, data });
const FREE = { kind: "free", text: "Buổi học tự do. Bài nộp không gắn phần đề cương." } as const;

beforeEach(() => {
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("end-of-session pop-up (mockup session-end)", () => {
  it("has a plum band with the cheering mascot, the praise title and two buttons, Về trang chủ first", () => {
    render(<SessionEndDialog open recorded={3} onHome={() => undefined} onMore={() => undefined} />);
    const dialog = screen.getByRole("dialog");
    expect(dialog.querySelector('[data-tier="field"]')).not.toBeNull();
    expect(dialog.querySelector('[data-mascot="khen"]')).not.toBeNull();
    expect(dialog.textContent).toContain(END_COPY.title);
    expect(dialog.textContent).toContain(END_COPY.recorded(3));
    // No duration of study anywhere: no pressure metrics (PRD US-11).
    expect(dialog.textContent).not.toMatch(/\d+\s*(giờ|phút)/);
    const buttons = screen.getAllByRole("button").map((b) => b.textContent);
    expect(buttons).toEqual([END_COPY.home, END_COPY.more]);
  });

  it("the empty variant shows the waiting mascot and no praise", () => {
    render(<SessionEndDialog open empty onHome={() => undefined} onMore={() => undefined} />);
    const dialog = screen.getByRole("dialog");
    expect(dialog.querySelector('[data-mascot="cho"]')).not.toBeNull();
    expect(dialog.textContent).toContain(END_COPY.emptyTitle);
    expect(dialog.textContent).not.toContain(END_COPY.title);
  });
});

describe("session screen (mockup session)", () => {
  it("in piece mode: one plum column with the one Kết thúc buổi học, the pieces as white sheets", async () => {
    const api = {
      sessionId: "s1",
      pieces: vi.fn(() => ok({ pieces: [{ id: "p1", position: 0, text: "học TCP", fileCount: 0 }], submitted: false })),
      addPiece: vi.fn(),
      removePiece: vi.fn(),
      complete: vi.fn(),
      submit: vi.fn(),
      upload: vi.fn(),
      result: vi.fn(),
    };
    const initial: SessionInitial = { round: { ...initialRound }, text: "", mentions: [], files: [] };
    render(
      <SessionScreen api={api as unknown as SessionApi} subject="Mạng máy tính" subjectId="SUBJ" stopHref="/today" docs={[]} suggestion={FREE} nextSuggestion={FREE} initial={initial} />,
    );
    await screen.findByText("Phần 1");
    expect(screen.getAllByRole("button", { name: "Kết thúc buổi học" })).toHaveLength(1);
    const column = document.querySelector('aside[data-tier="field"]');
    expect(column).not.toBeNull();
    expect(column?.textContent).toContain("Kết thúc buổi học");
    expect(column?.textContent).toContain("Đã ghi lại 1 lần");
    expect(screen.getByText("Bạn đã học gì?").closest("section")?.className).toContain("bg-sheet");
  });
});

describe("cards of a session (mockup vault-session)", () => {
  const cards = [
    { id: "c1", title: "Quy tắc cộng", content: "m + n", kind: "concept", anchors: [] },
    { id: "c2", title: "Quy tắc nhân", content: "m × n", kind: "concept", anchors: [] },
  ];

  it("is a horizontal band: a plum stage, one white sheet per card, round buttons, a position", () => {
    render(<CardList cards={cards} />);
    expect(document.querySelector('[data-vault-stage][data-tier="field"]')).not.toBeNull();
    expect(screen.getByRole("region", { name: "Thẻ của buổi học" })).toBeTruthy();
    expect(document.querySelectorAll('[data-slot="vault-card"]')).toHaveLength(2);
    for (const el of document.querySelectorAll('[data-slot="vault-card"]')) {
      expect(el.className).toContain("bg-sheet");
      expect(el.tagName).toBe("ARTICLE");
    }
    expect(screen.getByRole("button", { name: "Thẻ trước" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Thẻ sau" })).toBeTruthy();
    expect(screen.getByText("1 / 2")).toBeTruthy();
  });

  it("an empty session says so on a white sheet, no stage", () => {
    render(<CardList cards={[]} />);
    expect(screen.getByText("Buổi này chưa có thẻ nào.")).toBeTruthy();
    expect(document.querySelector("[data-vault-stage]")).toBeNull();
  });
});

describe("no hard-coded colour in the lane's folders", () => {
  const roots = ["components/session-study", "components/vault", "app/kho-kien-thuc"];
  const files = (dir: string): string[] =>
    readdirSync(path.join(__dirname, "..", dir), { withFileTypes: true }).flatMap((e) =>
      e.isDirectory() ? files(path.join(dir, e.name)) : /\.(tsx?|css)$/.test(e.name) ? [path.join(dir, e.name)] : [],
    );
  it("uses tokens only (no #hex, no rgb())", () => {
    for (const file of roots.flatMap(files)) {
      const src = readFileSync(path.join(__dirname, "..", file), "utf8");
      expect(src.match(/#[0-9a-fA-F]{3,8}\b|\brgba?\(/g) ?? [], file).toEqual([]);
    }
  });
});
