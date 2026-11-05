// @vitest-environment jsdom
// UI-A (ux-director 05/11): the subjects screen has one big number, the days to the soonest exam ahead.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SubjectList } from "@/components/subjects/subject-list";
import { pick } from "./subject-menu-helpers";

const s = (id: string, name: string, days: number) => ({ id, name, exam_date: "2026-12-15", days_until_exam: days, has_history: false });
afterEach(cleanup);

describe("SubjectList next exam", () => {
  it("shows the smallest positive days-left with a button into that subject", async () => {
    render(<SubjectList subjects={[s("a", "Toán", 40), s("b", "Vật lý", 12), s("c", "Hóa", -3)]} example="15/12/2031" />);
    const aside = screen.getByRole("complementary", { name: "Kỳ thi gần nhất" });
    expect(within(aside).getByText("12")).toBeTruthy();
    expect(within(aside).getByRole("link", { name: /Vào Vật lý/ }).getAttribute("href")).toBe("/subjects/b");
  });
  it("is absent when every exam is over", async () => {
    render(<SubjectList subjects={[s("c", "Hóa", -3)]} example="15/12/2031" />);
    expect(screen.queryByRole("complementary")).toBeNull();
  });
  it("counts an exam today, and its link is not a second solid button", async () => {
    render(<SubjectList subjects={[s("a", "Toán", 0), s("b", "Vật lý", 12)]} example="15/12/2031" />);
    const aside = screen.getByRole("complementary", { name: "Kỳ thi gần nhất" });
    expect(within(aside).getByText("Hôm nay")).toBeTruthy();
    expect(within(aside).getByRole("link", { name: /Vào Toán/ }).className).not.toContain("bg-hong");
  });
  // Q12 (QA 05/11): saving an edit refreshes the block (days left and the name in the link).
  it("refreshes after a saved edit of the exam date and the name", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ subject: { ...s("b", "Vật lý 2", 5), exam_date: "2026-11-10" } })),
    );
    render(<SubjectList subjects={[s("a", "Toán", 40), s("b", "Vật lý", 12)]} example="15/12/2031" />);
    const aside = () => screen.getByRole("complementary", { name: "Kỳ thi gần nhất" });
    expect(within(aside()).getByText("12")).toBeTruthy();
    await pick("Sửa", "Vật lý");
    fireEvent.change(screen.getByLabelText("Môn"), { target: { value: "Vật lý 2" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(within(aside()).getByText("5")).toBeTruthy());
    expect(within(aside()).getByRole("link", { name: /Vào Vật lý 2/ })).toBeTruthy();
  });
});
