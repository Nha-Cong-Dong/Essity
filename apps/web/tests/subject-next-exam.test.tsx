// @vitest-environment jsdom
// UI-A (ux-director 05/11): the subjects screen has one big number, the days to the soonest exam ahead.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SubjectList } from "@/components/subjects/subject-list";

const s = (id: string, name: string, days: number) => ({ id, name, exam_date: "2026-12-15", days_until_exam: days, has_history: false });
afterEach(cleanup);

describe("SubjectList next exam", () => {
  it("shows the smallest positive days-left with a button into that subject", () => {
    render(<SubjectList subjects={[s("a", "Toán", 40), s("b", "Vật lý", 12), s("c", "Hóa", -3)]} example="15/12/2031" />);
    const aside = screen.getByRole("complementary", { name: "Kỳ thi gần nhất" });
    expect(within(aside).getByText("12")).toBeTruthy();
    expect(within(aside).getByRole("button", { name: /Vào Vật lý/ }).getAttribute("href")).toBe("/subjects/b");
  });
  it("is absent when every exam is over", () => {
    render(<SubjectList subjects={[s("c", "Hóa", -3)]} example="15/12/2031" />);
    expect(screen.queryByRole("complementary")).toBeNull();
  });
});
