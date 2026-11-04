// @vitest-environment jsdom
// V22 group 2: a 70-part outline needs a quick search and "Mở hết / Thu hết".
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SyllabusTree } from "@/components/syllabus/syllabus-tree";
import type { SyllabusNode } from "@/lib/syllabus/tree";

afterEach(cleanup);

const leaf = (id: string, title: string, page: number): SyllabusNode => ({
  id, title, from: page, to: page, done: false, excluded: false, children: [], version: 1,
}) as unknown as SyllabusNode;
const chapter = (id: string, title: string, children: SyllabusNode[]): SyllabusNode => ({
  id, title, from: 1, to: 99, done: false, excluded: false, children, version: 1,
}) as unknown as SyllabusNode;

const nodes = [
  chapter("c1", "Chương 1. Xác suất", [leaf("a", "1.1.1. Quy tắc cộng", 1), leaf("b", "1.1.3. Hoán vị", 2)]),
  chapter("c2", "Chương 2. Biến ngẫu nhiên", [leaf("c", "2.1. Kỳ vọng", 3)]),
];

function show() {
  return render(
    <SyllabusTree label="Đề cương" nodes={nodes} unit="page" total={99} onNodes={() => {}} say={() => {}} onEditing={() => {}} />,
  );
}

describe("outline quick search (V22 g2)", () => {
  // Red when: the search ignores accents/case, or hides the way down to a match.
  it("shows only the matching part and the chapter above it, accents ignored", () => {
    const { container } = show();
    fireEvent.change(screen.getByRole("searchbox", { name: "Tìm trong đề cương" }), { target: { value: "hoan VI" } });
    expect(container.querySelector('[data-node="b"]')).not.toBeNull();
    expect(container.querySelector('[data-node="c1"]')).not.toBeNull();
    expect(container.querySelector('[data-node="a"]')).toBeNull();
    expect(container.querySelector('[data-node="c2"]')).toBeNull();
  });

  it("says so when nothing matches", () => {
    show();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "zzz" } });
    expect(screen.getByText(/Không có phần nào khớp/)).toBeTruthy();
  });

  // Red when: "Mở hết" / "Thu hết" do not fold every chapter.
  it("opens and folds every chapter", () => {
    const { container } = show();
    fireEvent.click(screen.getByRole("button", { name: "Mở hết" }));
    expect(container.querySelector('[data-node="c"]')).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Thu hết" }));
    expect(container.querySelector('[data-node="c"]')).toBeNull();
    expect(container.querySelector('[data-node="a"]')).toBeNull();
  });
});

describe("outline keyboard while searching (V22 g2)", () => {
  // Red when: a search hides the active row and no row is a tab stop, or ArrowRight ignores the search's open branches.
  it("keeps one tab stop when the search hides the active row", () => {
    const { container } = show();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "ky vong" } });
    const stops = container.querySelectorAll('[role="treeitem"][tabindex="0"]');
    expect(stops.length).toBe(1);
    expect(stops[0].getAttribute("data-node")).toBe("c2");
  });

  it("ArrowRight on a branch shown open by the search moves to its child", () => {
    const { container } = show();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "ky vong" } });
    const branch = container.querySelector<HTMLElement>('[data-node="c2"]')!;
    branch.focus();
    fireEvent.keyDown(branch, { key: "ArrowRight" });
    expect(document.activeElement?.getAttribute("data-node")).toBe("c");
  });

  it("Thu het leaves a tab stop on the first row", () => {
    const { container } = show();
    fireEvent.click(screen.getByRole("button", { name: "Mở hết" }));
    container.querySelector<HTMLElement>('[data-node="b"]')!.focus();
    fireEvent.click(screen.getByRole("button", { name: "Thu hết" }));
    expect(container.querySelector('[role="treeitem"][tabindex="0"]')?.getAttribute("data-node")).toBe("c1");
  });

  // Red when: the next row is not the first unstudied part that counts for the exam.
  it("marks the first unstudied part that is on the exam as Tiếp theo", () => {
    const skipped = { ...leaf("x", "0.1. Ngoài đề thi", 1), excluded: true } as SyllabusNode;
    const done = { ...leaf("y", "0.2. Đã học", 2), done: true } as SyllabusNode;
    const { container } = render(
      <SyllabusTree label="Đề cương" nodes={[chapter("c0", "Chương 0", [skipped, done, leaf("z", "0.3. Phần kế", 3)])]} unit="page" total={9} onNodes={() => {}} say={() => {}} onEditing={() => {}} />,
    );
    const next = container.querySelectorAll("[data-state-cell]");
    const withNext = [...next].filter((n) => n.textContent?.includes("Tiếp theo"));
    expect(withNext.length).toBe(1);
    expect(withNext[0].closest("[data-node]")?.getAttribute("data-node")).toBe("z");
  });
});

describe("outline fold and editing (V22 g2)", () => {
  // Red when: ArrowLeft on a chapter shown open by the search does not fold it.
  it("ArrowLeft folds a chapter while searching", () => {
    const { container } = show();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "ky vong" } });
    const branch = container.querySelector<HTMLElement>('[data-node="c2"]')!;
    branch.focus();
    expect(container.querySelector('[data-node="c"]')).not.toBeNull();
    fireEvent.keyDown(branch, { key: "ArrowLeft" });
    expect(container.querySelector('[data-node="c"]')).toBeNull();
    fireEvent.keyDown(branch, { key: "ArrowRight" });
    expect(container.querySelector('[data-node="c"]')).not.toBeNull();
  });

  // Red when: "Thu hết" closes the panel but the screen still thinks a range is being edited.
  it("Thu het ends editing", () => {
    const onEditing = vi.fn();
    const { container } = render(
      <SyllabusTree label="Đề cương" nodes={nodes} unit="page" total={99} onNodes={() => {}} say={() => {}} onEditing={onEditing} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Mở hết" }));
    const row = container.querySelector<HTMLElement>('[data-node="a"]')!;
    fireEvent.keyDown(row, { key: "Enter" });
    fireEvent.click(screen.getByRole("button", { name: /Sửa khoảng/ }));
    expect(onEditing).toHaveBeenLastCalledWith(true);
    fireEvent.click(screen.getByRole("button", { name: "Thu hết" }));
    expect(onEditing).toHaveBeenLastCalledWith(false);
  });
});
