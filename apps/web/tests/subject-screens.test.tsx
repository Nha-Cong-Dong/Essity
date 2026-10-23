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
// A year no fixed text has: the field and its message must follow the page's example (R24).
const EXAMPLE = "15/12/2031";

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
    render(<NewSubjectForm example={EXAMPLE} />);
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

  it("plan K17: core-api's exam_date_too_far shows its sentence under the date (approved 23/10, R09)", async () => {
    fakeWeb(() => Response.json({ error: "exam_date_too_far" }, { status: 422 }));
    fireEvent.change(name(), { target: { value: "Mạng" } });
    fireEvent.change(date(), { target: { value: "15/12/2062" } });

    fireEvent.click(screen.getByRole("button", { name: "Tạo môn" }));

    const sentence = await screen.findByText("Ngày thi cách quá xa (tối đa 2 năm). Kiểm tra lại năm nhé.");
    expect(sentence.closest("[data-copy]")).toBeNull();
    expect(date().getAttribute("aria-invalid")).toBe("true");
    expect(date().value).toBe("15/12/2062");
    expect(go).not.toHaveBeenCalled();
  });

  // Red when: the form treats a 401 as a network failure instead of sending the user to sign in
  // (review final 🟡).
  it("a session that ended sends the user to /login", async () => {
    fakeWeb(() => Response.json({ error: "signed_out" }, { status: 401 }));
    fireEvent.change(name(), { target: { value: "Mạng" } });
    fireEvent.change(date(), { target: { value: "15/12/2026" } });

    fireEvent.click(screen.getByRole("button", { name: "Tạo môn" }));

    await waitFor(() => expect(go).toHaveBeenCalledWith("/login"));
  });

  it("plan K10: 31/02/2027 is refused before sending", () => {
    const sent = fakeWeb(() => Response.json({ id: ID }, { status: 201 }));
    fireEvent.change(name(), { target: { value: "Mạng" } });
    fireEvent.change(date(), { target: { value: "31/02/2027" } });

    fireEvent.click(screen.getByRole("button", { name: "Tạo môn" }));

    expect(screen.getByText("Nhập ngày theo dạng ngày/tháng/năm, ví dụ 15/12/2031.")).toBeTruthy();
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
    render(<NewSubjectForm example={EXAMPLE} />);
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
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    const row = screen.getByText("Mạng máy tính").closest("li") as HTMLElement;
    expect(within(row).getByText("thi 15/12/2026")).toBeTruthy();
    expect(within(row).getByText("còn 54 ngày")).toBeTruthy();
  });

  it("no subject yet: DESIGN.md §6.8's empty state with a way to create one", () => {
    render(<SubjectList subjects={[]} example={EXAMPLE} />);
    expect(screen.getByText("Chưa có môn nào.")).toBeTruthy();
    // The project's link-as-button (Button render={<a/>}), as on the verify-email screen.
    expect(screen.getByText("Tạo môn").closest("a")?.getAttribute("href")).toBe("/subjects/new");
  });

  it("plan K2: \"Sửa\" edits in place and sends only what changed, then says \"Đã lưu.\"", async () => {
    const sent = fakeWeb(() =>
      Response.json({ subject: { ...MMT, exam_date: "2026-12-20", days_until_exam: 59 } }),
    );
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);

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
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);

    fireEvent.click(screen.getByRole("button", { name: "Sửa Mạng máy tính" }));
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

    await waitFor(() => expect(screen.queryByRole("button", { name: "Lưu" })).toBeNull());
    expect(sent).toHaveLength(0);
  });

  // Red when: a name typed as combining marks (Unikey "Unicode tổ hợp") counts as changed, though
  // core-api stores it composed (review c469b4d #2).
  it("plan K2: the same name in combining marks is no change", async () => {
    const sent = fakeWeb(() => Response.json({ subject: MMT }));
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);

    fireEvent.click(screen.getByRole("button", { name: "Sửa Mạng máy tính" }));
    fireEvent.change(name(), { target: { value: "Mạng máy tính".normalize("NFD") } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

    await waitFor(() => expect(screen.queryByRole("button", { name: "Lưu" })).toBeNull());
    expect(sent).toHaveLength(0);
  });

  it("plan K17: editing to a date too far shows the placeholder sentence under the date", async () => {
    fakeWeb(() => Response.json({ error: "exam_date_too_far" }, { status: 422 }));
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);

    fireEvent.click(screen.getByRole("button", { name: "Sửa Mạng máy tính" }));
    fireEvent.change(date(), { target: { value: "15/12/2062" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

    expect(await screen.findByText("Ngày thi cách quá xa (tối đa 2 năm). Kiểm tra lại năm nhé.")).toBeTruthy();
  });

  // Red when: a 404 (someone else's or a deleted subject, ADR-0001) is shown as a network failure
  // (review final 🟡).
  it("ADR-0001: a subject that is not found says so under the name", async () => {
    fakeWeb(() => Response.json({ error: "subject_not_found" }, { status: 404 }));
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);

    fireEvent.click(screen.getByRole("button", { name: "Sửa Mạng máy tính" }));
    fireEvent.change(name(), { target: { value: "Mạng máy tính 2" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

    expect(await screen.findByText("Không tìm thấy môn này. Tải lại trang rồi thử lại.")).toBeTruthy();
    expect(name().getAttribute("aria-invalid")).toBe("true");
  });

  // Red when: saving after the session ended stays on the page with a network sentence.
  it("editing after the session ended sends the user to /login", async () => {
    fakeWeb(() => Response.json({ error: "signed_out" }, { status: 401 }));
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);

    fireEvent.click(screen.getByRole("button", { name: "Sửa Mạng máy tính" }));
    fireEvent.change(name(), { target: { value: "Mạng máy tính 2" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

    await waitFor(() => expect(go).toHaveBeenCalledWith("/login"));
  });

  it("US-01 AC2: editing to a past date shows the sentence under the date", async () => {
    fakeWeb(() => Response.json({ error: "exam_date_not_in_future" }, { status: 422 }));
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);

    fireEvent.click(screen.getByRole("button", { name: "Sửa Mạng máy tính" }));
    fireEvent.change(date(), { target: { value: "02/10/2026" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

    expect(await screen.findByText("Ngày thi phải sau hôm nay.")).toBeTruthy();
  });
});

describe("the date example (risk register R24)", () => {
  // Red when: the field keeps a fixed "15/12/2026" placeholder.
  it("the new-subject field shows the page's example", () => {
    render(<NewSubjectForm example={EXAMPLE} />);
    expect(date().getAttribute("placeholder")).toBe(EXAMPLE);
  });

  // Red when: a message is shown without its example filled in (review 27b3601).
  it("no message ever shows the raw {example}", () => {
    render(<NewSubjectForm example={EXAMPLE} />);
    fireEvent.change(name(), { target: { value: "Mạng" } });
    fireEvent.change(date(), { target: { value: "31/02/2027" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo môn" }));
    expect(document.body.textContent).not.toContain("{example}");
    expect(document.body.textContent).toContain(EXAMPLE);
  });

  it("the edit field shows the same example", () => {
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    fireEvent.click(screen.getByRole("button", { name: "Sửa Mạng máy tính" }));
    expect(date().getAttribute("placeholder")).toBe(EXAMPLE);
  });
});

describe("SubjectList day count (DESIGN.md §6.8)", () => {
  it("\"còn N ngày\" is DESIGN's and is not a placeholder", () => {
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    expect(screen.getByText("còn 54 ngày").getAttribute("data-copy")).toBeNull();
  });

  // The user approved these on 23/10 (R09, T1.22): no placeholder mark left.
  it.each([
    [0, "thi hôm nay"],
    [-3, "đã thi"],
  ])("%i days: %s is shown as approved copy", (days, text) => {
    render(<SubjectList subjects={[{ ...MMT, days_until_exam: days }]} example={EXAMPLE} />);
    expect(screen.getByText(text).getAttribute("data-copy")).toBeNull();
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

  // Red when: the disabled zone tells the user to drop or pick a file it cannot take (flow-expert
  // 23/10, the same kind of untrue sentence as /today's before plan K16).
  it("US-01 AC7: asks for no action the page cannot do", () => {
    expect(screen.queryByText(/Thả file|bấm để chọn/)).toBeNull();
    expect(screen.getByText("Tải tài liệu sẽ có ở bản sau.")).toBeTruthy();
  });
});
