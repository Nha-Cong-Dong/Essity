// @vitest-environment jsdom
// QA2-WEB: focus and Escape while a subject row is in edit mode.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { pick } from "./subject-menu-helpers";

vi.mock("@/lib/navigate", () => ({ go: vi.fn() }));

const { SubjectList } = await import("@/components/subjects/subject-list");

const MMT = { id: "3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b", name: "Mạng máy tính", exam_date: "2026-12-15", days_until_exam: 54, has_history: false };

afterEach(cleanup);

describe("SubjectList edit focus", () => {
  it("\"Sửa\" puts focus in the name field", async () => {
    render(<SubjectList subjects={[MMT]} example="15/12/2031" />);
    await pick("Sửa", MMT.name);
    expect(document.activeElement).toBe(screen.getByLabelText("Môn"));
  });

  it("Escape leaves edit mode even when focus is outside the form, and returns focus to \"Sửa\"", async () => {
    render(<SubjectList subjects={[MMT]} example="15/12/2031" />);
    await pick("Sửa", MMT.name);
    (document.activeElement as HTMLElement).blur();
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByRole("button", { name: "Lưu" })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: `Tùy chọn môn ${MMT.name}` }));
  });

  it("\"Hủy\" returns focus to \"Sửa\"", async () => {
    render(<SubjectList subjects={[MMT]} example="15/12/2031" />);
    await pick("Sửa", MMT.name);
    fireEvent.click(screen.getByRole("button", { name: "Hủy" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: `Tùy chọn môn ${MMT.name}` }));
  });
});
