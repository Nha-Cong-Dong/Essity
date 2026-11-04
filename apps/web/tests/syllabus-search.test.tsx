// @vitest-environment jsdom
// V22 group 2: a 70-part outline needs a quick search and "Mở hết / Thu hết".
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

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
