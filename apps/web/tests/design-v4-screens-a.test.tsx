// @vitest-environment jsdom
// V4-SCREENS-A (DESIGN-V4 mockups today, subjects, subject-new, subject-detail): the field blocks, the sheets,
// the steps and the "⋯" menu, one rule at a time. Words and logic are covered by the older tests.
import { cleanup, render, screen, within } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";

import { CreateSteps } from "@/components/subjects/create-steps";
import { SubjectList } from "@/components/subjects/subject-list";
import { SubjectSuggestion } from "@/components/subjects/subject-suggestion";
import { TodayV2Screen } from "@/components/today-v2/today-v2-screen";
import { WeekStrip, weekFromCells } from "@/components/today-v2/week-strip";
import { SUBJECT_STATES, TODAY_STATES } from "@/lib/fixtures/today-v2";

afterEach(cleanup);

const fields = (markup: string) => (markup.match(/bg-field/g) ?? []).length;

describe("Hôm nay v4", () => {
  const week = weekFromCells([{ day: "2026-10-26", cardsSaved: 3, questionsAnswered: 1 }, { day: "2026-10-30", cardsSaved: 2, questionsAnswered: 0 }], "2026-10-30");

  it("the review is the field and, with a week under it, the two halves are one poster (review open at the foot)", () => {
    const html = renderToStaticMarkup(<TodayV2Screen today={TODAY_STATES.review} week={week} />);
    expect(html).toMatch(/aria-labelledby="today-review"[^>]*>|<section class="[^"]*bg-field[^"]*"[^>]*aria-labelledby="today-review"/);
    expect(html).toContain("border-bottom-left-radius:0");
    expect(html).toContain('data-tier="week"');
  });

  it("without a week the review keeps its rounded foot", () => {
    const html = renderToStaticMarkup(<TodayV2Screen today={TODAY_STATES.review} />);
    expect(html).not.toContain("border-bottom-left-radius:0");
  });

  it("the left column is white sheets, not tints; \"Học gì tiếp theo?\" keeps its words", () => {
    const html = renderToStaticMarkup(<TodayV2Screen today={TODAY_STATES.review} />);
    expect(html).not.toContain("bg-hong-tint");
    expect(html).toContain("Học gì tiếp theo?");
    expect(html).toContain("Gợi ý, bạn chọn");
    expect(html).toContain("Tiếp theo");
  });

  it("nothing due: the field says so and the star keeps its own corner (the title is kept clear of it)", () => {
    const html = renderToStaticMarkup(<TodayV2Screen today={TODAY_STATES["none-exams"]} week={week} />);
    expect(html).toContain("Xong phần ôn hôm nay");
    expect(html).toContain("max-w-[min(12ch,calc(100%-8.5rem))]");
  });

  it("today in Tuần này is pink with a ring (--now), never teal; a phone gets a white sheet", () => {
    const html = renderToStaticMarkup(<WeekStrip cells={week} today="2026-10-30" />);
    expect(html).toContain("bg-now");
    expect(html).toContain("min-[1024px]:bg-now-on-field");
    expect(html).not.toMatch(/accent-teal|bg-cam/);
    expect(html).toContain("bg-sheet");
  });
});

describe("Môn học v4", () => {
  const MMT = { id: "3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b", name: "Mạng máy tính", exam_date: "2026-12-15", days_until_exam: 54, has_history: false };
  const HDH = { id: "5d6e7f80-1a2b-4c3d-8e4f-5a6b7c8d9e0f", name: "Hệ điều hành", exam_date: "2027-01-10", days_until_exam: 80, has_history: false };

  it("one white sheet of rows, a letter tile each, one \"⋯\" menu each, and exactly one field (the nearest exam)", () => {
    const { container } = render(<SubjectList subjects={[MMT, HDH]} example="15/12/2031" />);
    const list = screen.getByRole("list");
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByRole("button", { name: "Tùy chọn môn Mạng máy tính" }).className).toContain("size-11");
    expect(within(list).queryByRole("button", { name: /^Sửa|^Xóa/ })).toBeNull();
    expect(screen.queryByText("+ Thêm môn")).toBeNull();
    expect(fields(container.innerHTML)).toBe(1);
    expect(screen.getByLabelText("Kỳ thi gần nhất").textContent).toContain("54");
  });

  it("no subject: the empty state is the field with the one \"Tạo môn\"; the header has none", () => {
    const { container } = render(<SubjectList subjects={[]} example="15/12/2031" />);
    expect(fields(container.innerHTML)).toBe(1);
    expect(screen.getAllByText("Tạo môn")).toHaveLength(1);
  });
});

describe("Tạo môn v4", () => {
  it("steps: three, the current one marked, a done step has a tick and a future one a number", () => {
    const { container } = render(<CreateSteps current={2} />);
    const items = within(screen.getByRole("list")).getAllByRole("listitem");
    expect(items.map((li) => li.textContent?.replace(/\d/g, "").trim())).toEqual(["Thông tin môn", "Giáo trình", "Đề cương"]);
    expect(items[1].getAttribute("aria-current")).toBe("step");
    expect(items[0].querySelector("svg")).not.toBeNull();
    expect(items[2].textContent).toContain("3");
    expect(fields(container.innerHTML)).toBe(1);
  });
});

describe("Môn cụ thể v4", () => {
  const draw = (state: string) =>
    renderToStaticMarkup(<SubjectSuggestion subjectId="s1" subjectName="Mạng máy tính" state={SUBJECT_STATES[state]} />);

  it("the suggestion is the one field; its title is the section; its button is the pale pink pair", () => {
    const html = draw("suggested");
    expect(fields(html)).toBe(1);
    expect(html).toContain("Phần 3.2");
    expect(html).toContain("--on-plum-action-bg");
  });

  it("no outline: the field says \"Chưa có đề cương\" and its one button is \"Tải giáo trình\"; no study button", () => {
    const html = draw("no-textbook");
    expect(html).toContain("Chưa có đề cương");
    expect(html).toContain("Tải giáo trình");
    expect(html).not.toContain("Học tự do");
    expect(html).not.toContain("Vào buổi học");
  });
});
