// @vitest-environment jsdom
// T2.3c (risk register R44, plan G15): "Tạo môn" shares a wrapping row with the title instead of a
// fixed -mt-16 pulled up beside it, so the frame is drawn by each state of /subjects: loading,
// failed, listed, empty. Each has exactly one h1; only a list has "Tạo môn" beside it (plan F9).
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw new Error(`redirect:${to}`);
  },
  notFound: () => {
    throw new Error("notFound");
  },
}));
vi.mock("@/lib/subjects", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/subjects")>();
  return {
    ...actual,
    listSubjects: async () => {
      throw new actual.CoreStatusError("/v1/subjects", 500);
    },
  };
});

const { SubjectList } = await import("@/components/subjects/subject-list");
const { SubjectsLoading } = await import("@/components/subjects/subjects-frame");
const { Subjects } = await import("@/components/subjects/subjects-loader");

const MMT = {
  id: "3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b",
  name: "Mạng máy tính",
  exam_date: "2026-12-15",
  days_until_exam: 54,
  has_history: false,
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const title = () => screen.getByRole("heading", { level: 1, name: "Môn học" });
const header = () => title().parentElement as HTMLElement;
// Base UI renders the button as an <a> with role="button": found by its words.
const creates = () => screen.queryAllByText("Tạo môn", { selector: "a" });

describe("/subjects frame (T2.3c, R44, plan G15)", () => {
  // Red when: "Tạo môn" is pulled up with -mt-16 again, or sits outside the title's row.
  it("a list: one h1, then Tạo môn in the same row, the only primary button", () => {
    render(<SubjectList subjects={[MMT]} example="15/12/2031" />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    const [create] = creates();
    expect(creates()).toHaveLength(1);
    expect(header().contains(create)).toBe(true);
    expect(title().compareDocumentPosition(create) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(header().className).toMatch(/(^| )flex-wrap( |$)/);
    expect(document.body.innerHTML).not.toMatch(/-mt-16/);
  });

  it("empty: one h1 with nothing beside it; Tạo môn is in the empty state", () => {
    render(<SubjectList subjects={[]} example="15/12/2031" />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(within(header()).queryByText("Tạo môn")).toBeNull();
    expect(creates()).toHaveLength(1);
    expect(header().contains(creates()[0])).toBe(false);
    // The row keeps the button's height without it, so the title sits where it does beside a list.
    expect(header().className).toMatch(/(^| )min-h-13( |$)/);
  });

  // Red when: the empty branch wraps the frame differently from the list (a fragment around it, as
  // before G15, or a key per branch), so React mounts a new h1 and focus or the screen reader's
  // place is lost when the last subject goes (tech-expert).
  it("deleting the last subject keeps the same h1 node and drops only Tạo môn from its row", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 204 })),
    );
    render(<SubjectList subjects={[MMT]} example="15/12/2031" />);
    const before = title();
    fireEvent.click(screen.getByRole("button", { name: `Sửa ${MMT.name}` }));
    fireEvent.click(screen.getByRole("button", { name: "Xóa môn" }));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Xóa môn" })));
    await screen.findByText("Đã xóa môn.");
    expect(title()).toBe(before);
    expect(within(header()).queryByText("Tạo môn")).toBeNull();
  });

  // Red when: the loading state has no title, so a slow network shows two grey blocks and a
  // screen reader no heading (design-critic, plan G15).
  it("loading: the title is there, with no button", () => {
    render(<SubjectsLoading />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(header().className).toMatch(/(^| )min-h-13( |$)/);
    expect(within(header()).queryByText("Tạo môn")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Đang tải danh sách môn.");
  });

  it("failed: the title is there above the alert, with no Tạo môn", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const markup = renderToStaticMarkup(await Subjects({ example: "15/12/2031" }));
    expect(markup.match(/<h1/g)).toHaveLength(1);
    expect(markup).toContain('role="alert"');
    expect(markup).not.toContain("Tạo môn");
  });
});
