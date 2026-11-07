// @vitest-environment jsdom
// GRAPH-V4-CANVAS: /graph as the v4 mockup draws it: a full-bleed canvas with a floating legend,
// zoom controls and a detail card; the empty state is a canvas, not a flat titled block.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DetailCard, GraphEmpty, GraphLegend, ZoomControls } from "@/components/graph/graph-overlays";

afterEach(cleanup);
const src = (p: string) => readFileSync(join(__dirname, "..", p), "utf8");

const topics = [
  { id: "a", name: "Xác suất", color: "#d1347a", cards: 4 },
  { id: "b", name: "Mạng", color: "#441125", cards: 2 },
];
const card = {
  id: "c1",
  title: "Công thức Bayes",
  body: "Tính ngược xác suất.",
  sectionId: "s",
  neededBy: [],
  subjectId: "sub1",
  anchors: [{ id: "x", label: "Giáo trình · trang 42", quote: "xác suất tiên nghiệm" }],
};

describe("GraphLegend", () => {
  it("names the cards count and each topic as a toggle with its count", () => {
    const onToggle = vi.fn();
    render(<GraphLegend topics={topics} hidden={new Set(["b"])} onToggle={onToggle} total={6} mode="subject" cardList={<li>x</li>} />);
    expect(screen.getByText("Đồ thị kiến thức")).toBeTruthy();
    const a = screen.getByRole("button", { name: /Xác suất/ });
    expect(a.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: /Mạng/ }).getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(a);
    expect(onToggle).toHaveBeenCalledWith("a");
  });
});

describe("ZoomControls", () => {
  it("has three 44px round icon buttons with Vietnamese labels", () => {
    const f = { in: vi.fn(), out: vi.fn(), fit: vi.fn() };
    render(<ZoomControls onIn={f.in} onOut={f.out} onFit={f.fit} />);
    for (const [name, fn] of [["Phóng to", f.in], ["Thu nhỏ", f.out], ["Vừa khung", f.fit]] as const) {
      const b = screen.getByRole("button", { name });
      expect(b.className).toContain("size-11");
      expect(b.className).toContain("rounded-full");
      fireEvent.click(b);
      expect(fn).toHaveBeenCalled();
    }
  });
});

describe("DetailCard", () => {
  it("is a non-modal card with meta, title, source block, related chips and the vault button", () => {
    const onClose = vi.fn();
    const onPick = vi.fn();
    render(<DetailCard card={card} subject="Xác suất" color="#d1347a" related={[{ id: "c2", title: "Quy tắc nhân" }]} onPick={onPick} onClose={onClose} />);
    expect(screen.getByRole("heading", { name: "Công thức Bayes" })).toBeTruthy();
    expect(screen.getByText(/Thẻ · Xác suất/)).toBeTruthy();
    expect(screen.getByText("Giáo trình · trang 42")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Quy tắc nhân" }));
    expect(onPick).toHaveBeenCalledWith("c2");
    expect(screen.getByRole("link", { name: "Mở trong Kho" }).getAttribute("href")).toBe("/kho-kien-thuc?subject=sub1");
    fireEvent.click(screen.getByRole("button", { name: "Đóng" }));
    expect(onClose).toHaveBeenCalled();
    expect(document.querySelector("dialog")).toBeNull();
  });
});

describe("GraphEmpty", () => {
  it("is a canvas with a mascot, one sentence and one action", () => {
    render(<GraphEmpty href="/subjects/s1/sessions/new" />);
    const root = document.querySelector("[data-empty]")!;
    expect(root.className).toContain("rounded-sheet");
    expect(screen.getByText(/Chưa có thẻ kiến thức nào/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Ghi buổi học" })).toBeTruthy();
  });
});

describe("wiring", () => {
  it("the real /graph drops the flat title row and draws a full-bleed canvas", () => {
    const page = src("app/graph/page.tsx");
    expect(page).toMatch(/<h1 className="sr-only/);
    expect(page).not.toContain('className="m-0 font-display text-title">Đồ thị tri thức');
    const kg = src("components/graph/knowledge-graph.tsx");
    expect(kg).toContain("GraphLegend");
    expect(kg).toContain("ZoomControls");
    expect(kg).toContain("DetailCard");
    expect(kg).not.toContain("<dialog");
    expect(kg).toContain("absolute inset-0");
  });
});
