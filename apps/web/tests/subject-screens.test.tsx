// @vitest-environment jsdom
// T1.20: creating, listing and editing subjects as the user meets them (US-01 AC1, AC2, AC7;
// DESIGN.md §6.8; plan K2, K5, K10).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const go = vi.fn();
vi.mock("@/lib/navigate", () => ({ go: (path: string) => go(path) }));

const { NewSubjectForm } = await import("@/components/subjects/new-subject-form");
const { SubjectList } = await import("@/components/subjects/subject-list");
const { UploadStep } = await import("@/components/subjects/upload-step");

const ID = "3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b";
const MMT = { id: ID, name: "Mạng máy tính", exam_date: "2026-12-15", days_until_exam: 54 };

type Sent = { path: string; method: string; body: unknown };

function fakeWeb(reply: (path: string) => Response) {
  const sent: Sent[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init: RequestInit = {}) => {
      sent.push({ path, method: init.method ?? "GET", body: init.body ? JSON.parse(String(init.body)) : undefined });
      return reply(path);
    }),
  );
  return sent;
}

const name = () => screen.getByLabelText("Môn") as HTMLInputElement;
const date = () => screen.getByLabelText("Ngày thi") as HTMLInputElement;

afterEach(cleanup);
beforeEach(() => go.mockReset());

describe("NewSubjectForm (US-01 AC1, AC2, AC7)", () => {
  beforeEach(() => {
    render(<NewSubjectForm />);
  });

  it("US-01 AC1: exactly two fields, name and exam date, posted", () => {
    const form = name().closest("form") as HTMLFormElement;
    expect(form.querySelectorAll("input:not([type=date]), select, textarea")).toHaveLength(2);
    expect(form.getAttribute("method")).toBe("post"); // review plan R2
  });

  it("US-01 AC1, AC7: creating sends name and ISO date, then goes to the upload step", async () => {
    const sent = fakeWeb(() => Response.json({ id: ID }, { status: 201 }));
    fireEvent.change(name(), { target: { value: "Mạng máy tính" } });
    fireEvent.change(date(), { target: { value: "15/12/2026" } });

    fireEvent.click(screen.getByRole("button", { name: "Tạo môn" }));

    await waitFor(() => expect(go).toHaveBeenCalledWith(`/subjects/${ID}/upload`));
    expect(sent).toEqual([
      { path: "/api/subjects", method: "POST", body: { name: "Mạng máy tính", exam_date: "2026-12-15" } },
    ]);
  });

  // Red when: the form follows an id it did not check (review plan R3).
  it("an id that is not a UUID goes to /subjects instead", async () => {
    fakeWeb(() => Response.json({ id: "../me" }, { status: 201 }));
    fireEvent.change(name(), { target: { value: "Mạng" } });
    fireEvent.change(date(), { target: { value: "15/12/2026" } });

    fireEvent.click(screen.getByRole("button", { name: "Tạo môn" }));

    await waitFor(() => expect(go).toHaveBeenCalledWith("/subjects"));
  });

  it("US-01 AC2: core-api's exam_date_not_in_future shows DESIGN's sentence under the date", async () => {
    fakeWeb(() => Response.json({ error: "exam_date_not_in_future" }, { status: 422 }));
    fireEvent.change(name(), { target: { value: "Mạng" } });
    fireEvent.change(date(), { target: { value: "02/10/2026" } });

    fireEvent.click(screen.getByRole("button", { name: "Tạo môn" }));

    expect(await screen.findByText("Ngày thi phải sau hôm nay.")).toBeTruthy();
    expect(date().getAttribute("aria-invalid")).toBe("true");
    expect(date().getAttribute("aria-describedby")).toBe("exam-date-error");
    expect(go).not.toHaveBeenCalled();
  });

  it("plan K10: 31/02/2027 is refused before sending", () => {
    const sent = fakeWeb(() => Response.json({ id: ID }, { status: 201 }));
    fireEvent.change(name(), { target: { value: "Mạng" } });
    fireEvent.change(date(), { target: { value: "31/02/2027" } });

    fireEvent.click(screen.getByRole("button", { name: "Tạo môn" }));

    expect(screen.getByText("Nhập ngày theo dạng ngày/tháng/năm, ví dụ 15/12/2026.")).toBeTruthy();
    expect(sent).toHaveLength(0);
  });

  it("an empty name asks for one and sends nothing", () => {
    const sent = fakeWeb(() => Response.json({ id: ID }, { status: 201 }));
    fireEvent.change(date(), { target: { value: "15/12/2026" } });

    fireEvent.click(screen.getByRole("button", { name: "Tạo môn" }));

    expect(screen.getByText("Nhập tên môn, ví dụ Mạng máy tính.")).toBeTruthy();
    expect(name().getAttribute("aria-invalid")).toBe("true");
    expect(sent).toHaveLength(0);
  });

  // Red when: a browser without showPicker (jsdom has none) shows a button that does nothing.
  it("plan K10: without showPicker there is no calendar button, and the typed field works", () => {
    expect(screen.queryByRole("button", { name: "Chọn ngày trên lịch" })).toBeNull();
    fireEvent.change(date(), { target: { value: "15/12/2026" } });
    expect(date().value).toBe("15/12/2026");
  });
});

describe("NewSubjectForm calendar (plan K10, where showPicker exists)", () => {
  const showPicker = vi.fn();
  beforeEach(() => {
    showPicker.mockReset();
    Object.defineProperty(HTMLInputElement.prototype, "showPicker", { value: showPicker, configurable: true });
    render(<NewSubjectForm />);
  });
  afterEach(() => {
    delete (HTMLInputElement.prototype as { showPicker?: unknown }).showPicker;
  });

  it("the button opens the calendar of a hidden, unnamed date input", () => {
    fireEvent.click(screen.getByRole("button", { name: "Chọn ngày trên lịch" }));

    expect(showPicker).toHaveBeenCalledTimes(1);
    const picker = document.querySelector('input[type="date"]') as HTMLInputElement;
    expect(picker.getAttribute("aria-hidden")).toBe("true");
    expect(picker.tabIndex).toBe(-1);
    expect(picker.hasAttribute("name")).toBe(false); // the text field is the only value sent
    expect(picker.hasAttribute("min")).toBe(false); // the learning day, not the clock, decides
  });

  it("a picked date is written day/month/year and focus returns to the field", () => {
    const picker = document.querySelector('input[type="date"]') as HTMLInputElement;

    fireEvent.change(picker, { target: { value: "2026-12-15" } });

    expect(date().value).toBe("15/12/2026");
    expect(document.activeElement).toBe(date());
  });

  it("a typed date opens the calendar on that date", () => {
    fireEvent.change(date(), { target: { value: "15/12/2026" } });

    expect((document.querySelector('input[type="date"]') as HTMLInputElement).value).toBe("2026-12-15");
  });

  it("a calendar that refuses to open sends focus back to the field, with no error shown", () => {
    showPicker.mockImplementation(() => {
      throw new DOMException("no", "NotAllowedError");
    });

    fireEvent.click(screen.getByRole("button", { name: "Chọn ngày trên lịch" }));

    expect(document.activeElement).toBe(date());
  });
});

describe("SubjectList (T1.20, plan K2, K3)", () => {
  it("each subject shows its name, exam date and core-api's days left", () => {
    render(<SubjectList subjects={[MMT]} />);
    const row = screen.getByText("Mạng máy tính").closest("li") as HTMLElement;
    expect(within(row).getByText("thi 15/12/2026")).toBeTruthy();
    expect(within(row).getByText("còn 54 ngày")).toBeTruthy();
  });

  it("no subject yet: DESIGN.md §6.8's empty state with a way to create one", () => {
    render(<SubjectList subjects={[]} />);
    expect(screen.getByText("Chưa có môn nào.")).toBeTruthy();
    // The project's link-as-button (Button render={<a/>}), as on the verify-email screen.
    expect(screen.getByText("Tạo môn").closest("a")?.getAttribute("href")).toBe("/subjects/new");
  });

  it("plan K2: \"Sửa\" edits in place and sends only what changed, then says \"Đã lưu.\"", async () => {
    const sent = fakeWeb(() =>
      Response.json({ subject: { ...MMT, exam_date: "2026-12-20", days_until_exam: 59 } }),
    );
    render(<SubjectList subjects={[MMT]} />);

    fireEvent.click(screen.getByRole("button", { name: "Sửa Mạng máy tính" }));
    fireEvent.change(date(), { target: { value: "20/12/2026" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

    expect(await screen.findByText("Đã lưu.")).toBeTruthy();
    expect(sent).toEqual([{ path: `/api/subjects/${ID}`, method: "PATCH", body: { exam_date: "2026-12-20" } }]);
    expect(screen.getByText("thi 20/12/2026")).toBeTruthy();
    expect(screen.getByText("còn 59 ngày")).toBeTruthy();
  });

  it("plan K2: nothing changed → nothing sent, the form closes", async () => {
    const sent = fakeWeb(() => Response.json({ subject: MMT }));
    render(<SubjectList subjects={[MMT]} />);

    fireEvent.click(screen.getByRole("button", { name: "Sửa Mạng máy tính" }));
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

    await waitFor(() => expect(screen.queryByRole("button", { name: "Lưu" })).toBeNull());
    expect(sent).toHaveLength(0);
  });

  it("US-01 AC2: editing to a past date shows the sentence under the date", async () => {
    fakeWeb(() => Response.json({ error: "exam_date_not_in_future" }, { status: 422 }));
    render(<SubjectList subjects={[MMT]} />);

    fireEvent.click(screen.getByRole("button", { name: "Sửa Mạng máy tính" }));
    fireEvent.change(date(), { target: { value: "02/10/2026" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

    expect(await screen.findByText("Ngày thi phải sau hôm nay.")).toBeTruthy();
  });
});

describe("UploadStep (US-01 AC7, plan K5)", () => {
  beforeEach(() => {
    render(<UploadStep name="Mạng máy tính" />);
  });

  it("US-01 AC7: names the subject, says \"Sắp có\", and offers \"Làm sau\" back to /subjects", () => {
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Tải tài liệu cho Mạng máy tính");
    expect(screen.getByText("Sắp có")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Làm sau" }).getAttribute("href")).toBe("/subjects");
  });

  // Red when: a real uploader lands before T4.6, or the drop zone looks usable.
  it("US-01 AC7: the drop zone is disabled and there is no file input", () => {
    expect(document.querySelector('input[type="file"]')).toBeNull();
    expect(document.querySelector('[aria-disabled="true"]')).not.toBeNull();
  });
});
