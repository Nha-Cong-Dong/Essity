// @vitest-environment jsdom
// T2.3c (risk register R44, plan G3, G9): what a subject row says and how its date line is built;
// where things land on screen is measured by e2e/layout.spec.ts.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SubjectList } from "@/components/subjects/subject-list";

const MMT = {
  id: "3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b",
  name: "Mạng máy tính",
  exam_date: "2026-12-15",
  days_until_exam: 54,
  has_history: false,
};

afterEach(cleanup);

function dateLine() {
  render(<SubjectList subjects={[MMT]} example="15/12/2031" />);
  const exam = screen.getByText("thi 15/12/2026");
  return { exam, left: screen.getByText("còn 54 ngày"), line: exam.parentElement as HTMLElement };
}

describe("subject row (T2.3c, R44)", () => {
  // Red when: the two halves touch with no space between them, so a screen reader reads
  // "thi 15/12/2026còn 54 ngày" as one word (plan G9).
  it("R44-g the date line reads with a space between its halves", () => {
    const { line } = dateLine();
    expect(line.textContent).toBe("thi 15/12/2026 còn 54 ngày");
  });

  // Red when: a half can break inside itself ("thi" alone on a line) or both halves share a colour.
  it("R44-g each half stays on one line; the exam date in ink, the days left softer", () => {
    const { exam, left } = dateLine();
    for (const half of [exam, left]) expect(half.className).toMatch(/\bwhitespace-nowrap\b/);
    expect(exam.className).not.toMatch(/text-ink-soft/);
    expect(left.className).toMatch(/\btext-ink-soft\b/);
  });

  // Red when: the name cannot break inside a long word, which then spills over the date (R44).
  it("R44-b the name breaks anywhere it has to and keeps the id the row's labels point at", () => {
    render(<SubjectList subjects={[MMT]} example="15/12/2031" />);
    const name = screen.getByText("Mạng máy tính");
    expect(name.className).toMatch(/\bwrap-anywhere\b/);
    expect(name.id).toBe(`subject-${MMT.id}-name`);
    const row = name.closest("li") as HTMLElement;
    expect(within(row).getByRole("button", { name: "Sửa Mạng máy tính" })).toBeTruthy();
  });
});

describe("subject row link (T7.13 review F1)", () => {
  // Red when: the subject's name is not a link to its screen (the milestone walk needs it).
  it("US-15 AC6: the name links to /subjects/[id]", () => {
    render(<SubjectList subjects={[MMT]} example="15/12/2031" />);
    const link = screen.getByRole("link", { name: "Mạng máy tính" });
    expect(link.getAttribute("href")).toBe(`/subjects/${MMT.id}`);
  });
});
