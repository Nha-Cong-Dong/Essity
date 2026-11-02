// @vitest-environment jsdom
// T2.3b: deleting a subject from /subjects (us-01 AC8). Flow: PLAN T2.3b; design: plan F7, F9
// (design-director and design-critic, flow-expert). Its sentences were placeholders (R09) until
// the user approved them on 25/10 (T2.3c).
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const go = vi.fn();
vi.mock("@/lib/navigate", () => ({ go: (path: string) => go(path) }));

const { SubjectList } = await import("@/components/subjects/subject-list");

const MMT = { id: "3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b", name: "Mạng máy tính", exam_date: "2026-12-15", days_until_exam: 54, has_history: false };
const HDH = { id: "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d", name: "Hệ điều hành", exam_date: "2026-12-20", days_until_exam: 59, has_history: false };
const EXAMPLE = "15/12/2031";
const CONFIRM = "Xóa môn này khỏi danh sách và phiên ôn?";
const DELETED = "Đã xóa môn.";
const HAS_HISTORY = "Môn này đã có bài ôn nên chưa xóa được ở đây.";

type Sent = { path: string; method: string };

/** web's routes: `reply` answers each call, in order of the list when given several. */
function fakeWeb(...replies: (() => Response | Promise<Response>)[]) {
  const sent: Sent[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init: RequestInit = {}) => {
      sent.push({ path, method: init.method ?? "GET" });
      const reply = replies[Math.min(sent.length - 1, replies.length - 1)];
      return reply();
    }),
  );
  return sent;
}

const row = (name: string) => screen.getByText(name, { selector: "a" }).closest("li") as HTMLElement;
const openEdit = (name: string) => fireEvent.click(screen.getByRole("button", { name: `Sửa ${name}` }));
const deleteButton = (scope: HTMLElement = document.body) => within(scope).getByRole("button", { name: "Xóa môn" });
const keepButton = () => screen.getByRole("button", { name: "Giữ môn" });
const empty204 = () => new Response(null, { status: 204 });

function openConfirm(name: string) {
  openEdit(name);
  fireEvent.click(deleteButton(row(name)));
}

afterEach(cleanup);
beforeEach(() => go.mockReset());

describe("SubjectList delete (T2.3b, us-01 AC8)", () => {
  it("us-01 AC8: a subject with no history has \"Xóa môn\" in its edit form, under a rule, apart from Lưu", () => {
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    openEdit(MMT.name);
    const button = deleteButton(row(MMT.name));
    expect(button.closest("form")).toBeNull();
    expect(button.parentElement?.className).toContain("border-t");
    // Several rows can be open at once: the subject's name tells the buttons apart.
    const describedBy = button.getAttribute("aria-describedby") ?? "";
    expect(document.getElementById(describedBy)?.textContent).toBe(MMT.name);
  });

  it("us-01 AC8: a subject with history has no delete button but a line saying why", () => {
    render(<SubjectList subjects={[{ ...MMT, has_history: true }]} example={EXAMPLE} />);
    openEdit(MMT.name);
    expect(within(row(MMT.name)).queryByRole("button", { name: "Xóa môn" })).toBeNull();
    expect(within(row(MMT.name)).getByText(HAS_HISTORY)).toBeTruthy();
  });

  it("us-01 AC8: \"Xóa môn\" turns the form into a confirmation in place, focus on \"Giữ môn\"", () => {
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    openConfirm(MMT.name);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByLabelText("Môn")).toBeNull();
    const group = screen.getByRole("group");
    expect(group.getAttribute("aria-labelledby")?.split(" ")).toHaveLength(2);
    expect(group.textContent).toContain(CONFIRM);
    expect(document.activeElement).toBe(keepButton());
    // Not an error: the sentence is in ink, not the error colour.
    expect(screen.getByText(CONFIRM).className).not.toContain("text-partial");
  });

  it.each([
    ["Giữ môn", () => fireEvent.click(keepButton())],
    ["Escape", () => fireEvent.keyDown(screen.getByRole("group"), { key: "Escape" })],
  ])("us-01 AC8: %s goes back to the form with what was typed, focus on \"Xóa môn\"", (_, keep) => {
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    openEdit(MMT.name);
    fireEvent.change(screen.getByLabelText("Môn"), { target: { value: "Mạng 2" } });
    fireEvent.click(deleteButton(row(MMT.name)));
    keep();
    expect((screen.getByLabelText("Môn") as HTMLInputElement).value).toBe("Mạng 2");
    expect(document.activeElement).toBe(deleteButton(row(MMT.name)));
  });

  it("us-01 AC8: deleting sends one DELETE; the row becomes \"Đã xóa môn.\" with no name, focused", async () => {
    const sent = fakeWeb(empty204);
    render(<SubjectList subjects={[MMT, HDH]} example={EXAMPLE} />);
    openConfirm(MMT.name);
    fireEvent.click(deleteButton());
    fireEvent.click(deleteButton());

    const placeholder = await screen.findByText(DELETED);
    expect(sent).toEqual([{ path: `/api/subjects/${MMT.id}`, method: "DELETE" }]);
    expect(screen.queryByText(MMT.name)).toBeNull();
    const li = placeholder.closest("li") as HTMLElement;
    expect(within(li).queryAllByRole("button")).toHaveLength(0);
    await waitFor(() => expect(document.activeElement).toBe(placeholder));
    // Read once, through focus: not inside a live region as well.
    expect(placeholder.closest("[role=status],[aria-live]")).toBeNull();
  });

  it("us-01 AC8: a subject already gone (404) is taken as deleted, no error", async () => {
    fakeWeb(() => Response.json({ error: "subject_not_found" }, { status: 404 }));
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    openConfirm(MMT.name);
    fireEvent.click(deleteButton());
    expect(await screen.findByText(DELETED)).toBeTruthy();
    expect(screen.queryByText("Chưa gửi được. Kiểm tra kết nối rồi thử lại.")).toBeNull();
  });

  it("us-01 AC8: one placeholder at a time; opening \"Sửa\" anywhere clears it", async () => {
    fakeWeb(empty204);
    render(<SubjectList subjects={[MMT, HDH]} example={EXAMPLE} />);
    openConfirm(MMT.name);
    fireEvent.click(deleteButton());
    await screen.findByText(DELETED);

    openConfirm(HDH.name);
    expect(screen.queryByText(DELETED)).toBeNull();
    fireEvent.click(deleteButton());
    const second = await screen.findByText(DELETED);
    expect(screen.getAllByText(DELETED)).toHaveLength(1);
    await waitFor(() => expect(document.activeElement).toBe(second));
  });

  // Red when: the list drops the old placeholder from a stale render's state, so two deletes in
  // flight at once bring the first subject back as a live row (review 1ac2df7 #1).
  it("us-01 AC8: two deletes answered one after the other leave neither subject listed", async () => {
    const answers: ((response: Response) => void)[] = [];
    fakeWeb(() => new Promise<Response>((resolve) => answers.push(resolve)));
    const X = { ...HDH, id: "9a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d", name: "Xác suất" };
    render(<SubjectList subjects={[MMT, HDH, X]} example={EXAMPLE} />);
    openEdit(MMT.name);
    openEdit(HDH.name);
    fireEvent.click(deleteButton(row(MMT.name)));
    fireEvent.click(deleteButton(row(HDH.name)));
    const [first, second] = screen.getAllByRole("group");
    fireEvent.click(deleteButton(first));
    fireEvent.click(deleteButton(second));
    expect(answers).toHaveLength(2);

    await act(async () => answers[0](empty204()));
    await act(async () => answers[1](empty204()));

    expect(screen.queryByText(MMT.name)).toBeNull();
    expect(screen.queryByText(HDH.name)).toBeNull();
    expect(screen.getAllByText(DELETED)).toHaveLength(1);
    expect(screen.getByText(X.name)).toBeTruthy();
  });

  it("us-01 AC8: deleting the last subject shows the placeholder above the empty state, one \"Tạo môn\"", async () => {
    fakeWeb(empty204);
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    expect(screen.getAllByText("Tạo môn")).toHaveLength(1);
    openConfirm(MMT.name);
    fireEvent.click(deleteButton());

    const placeholder = await screen.findByText(DELETED);
    expect(screen.getByText("Chưa có môn nào.")).toBeTruthy();
    expect(screen.getAllByText("Tạo môn")).toHaveLength(1);
    expect(placeholder.compareDocumentPosition(screen.getByText("Chưa có môn nào.")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("us-01 AC8: history found on delete (409) shows the line in place of the button, focused", async () => {
    fakeWeb(() => Response.json({ error: "subject_has_history" }, { status: 409 }));
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    openConfirm(MMT.name);
    fireEvent.click(deleteButton());

    const line = await screen.findByText(HAS_HISTORY);
    expect(screen.queryByRole("group")).toBeNull();
    expect(screen.queryByText(DELETED)).toBeNull();
    expect(within(row(MMT.name)).queryByRole("button", { name: "Xóa môn" })).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(line));
  });

  it.each([0, 403, 500, 503])(
    "us-01 AC8: no answer or %s keeps the confirmation, says so in an alert, and can be pressed again",
    async (status) => {
      const sent = fakeWeb(
        status === 0
          ? () => Promise.reject(new TypeError("fetch failed"))
          : () => Response.json({ error: "unavailable" }, { status }),
        empty204,
      );
      render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
      openConfirm(MMT.name);
      fireEvent.click(deleteButton());

      const alert = await screen.findByRole("alert");
      expect(alert.textContent).toContain("Chưa gửi được. Kiểm tra kết nối rồi thử lại.");
      const button = deleteButton(screen.getByRole("group"));
      expect(document.getElementById(button.getAttribute("aria-describedby") ?? "")).toBeTruthy();
      fireEvent.click(button);
      expect(await screen.findByText(DELETED)).toBeTruthy();
      expect(sent).toHaveLength(2);
    },
  );

  it("us-01 AC8: while deleting, \"Giữ môn\" is disabled and Escape does nothing", async () => {
    let answer: (response: Response) => void = () => {};
    fakeWeb(() => new Promise<Response>((resolve) => (answer = resolve)));
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    openConfirm(MMT.name);
    fireEvent.click(deleteButton());

    expect((keepButton() as HTMLButtonElement).disabled).toBe(true);
    fireEvent.keyDown(screen.getByRole("group"), { key: "Escape" });
    expect(screen.getByRole("group")).toBeTruthy();
    await act(async () => answer(empty204()));
    expect(await screen.findByText(DELETED)).toBeTruthy();
  });

  it("a session that ended sends the user to /login", async () => {
    fakeWeb(() => Response.json({ error: "signed_out" }, { status: 401 }));
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    openConfirm(MMT.name);
    fireEvent.click(deleteButton());
    await waitFor(() => expect(go).toHaveBeenCalledWith("/login"));
  });

  // The user approved the six strings on 25/10 (T2.3c plan G2): none is a placeholder any more.
  it("R09: the approved sentences carry no data-copy=\"tam\" in the page", async () => {
    fakeWeb(empty204);
    render(<SubjectList subjects={[MMT, { ...HDH, has_history: true }]} example={EXAMPLE} />);
    openEdit(HDH.name);
    expect(screen.getByText(HAS_HISTORY).getAttribute("data-copy")).toBeNull();
    openEdit(MMT.name);
    expect(deleteButton(row(MMT.name)).getAttribute("data-copy")).toBeNull();
    fireEvent.click(deleteButton(row(MMT.name)));
    expect(screen.getByText(CONFIRM).getAttribute("data-copy")).toBeNull();
    expect(deleteButton(screen.getByRole("group")).getAttribute("data-copy")).toBeNull();
    expect(keepButton().getAttribute("data-copy")).toBeNull();
    fireEvent.click(deleteButton(screen.getByRole("group")));
    expect((await screen.findByText(DELETED)).getAttribute("data-copy")).toBeNull();
  });
});

describe("SubjectList \"Đã lưu.\" (T1.20, kept by T2.3b plan F7)", () => {
  it("saving still says \"Đã lưu.\" in the row's status region, which is there before saving", async () => {
    fakeWeb(() => Response.json({ subject: { ...MMT, name: "Mạng" } }));
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    const region = within(row(MMT.name)).getByRole("status");
    expect(region.textContent).toBe("");
    openEdit(MMT.name);
    fireEvent.change(screen.getByLabelText("Môn"), { target: { value: "Mạng" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(region.textContent).toBe("Đã lưu."));
  });
});
