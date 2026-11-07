// @vitest-environment jsdom
// PREDEPLOY-FIX-A E-06: the 404 pages are Vietnamese and carry the navigation (root) or a way back (subject).
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import NotFound from "@/app/not-found";
import SubjectNotFound from "@/app/subjects/[id]/not-found";
import { NOT_FOUND_TITLE } from "@/components/not-found-body";

vi.mock("next/navigation", () => ({ usePathname: () => "/xyz", useRouter: () => ({ push: vi.fn() }) }));
afterEach(cleanup);

describe("E-06 not found", () => {
  it("E-06 root 404 is Vietnamese, with the main navigation and a way to Hôm nay", () => {
    render(<NotFound />);
    expect(screen.getByText(NOT_FOUND_TITLE)).toBeTruthy();
    expect(screen.queryByText(/This page could not be found/i)).toBeNull();
    expect(screen.getAllByRole("link", { name: /Môn học/ }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Về trang Hôm nay" }).getAttribute("href")).toBe("/today");
  });

  it("E-06 subject 404 (someone else's or unknown id) offers the subject list, no second shell", () => {
    render(<SubjectNotFound />);
    expect(screen.getByText(NOT_FOUND_TITLE)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Về danh sách môn học" }).getAttribute("href")).toBe("/subjects");
    expect(document.querySelector("header")).toBeNull();
  });
});
