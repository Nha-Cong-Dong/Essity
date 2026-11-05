// @vitest-environment jsdom
// T2.3b: deleting a subject from /subjects (us-01 AC8). Flow: PLAN T2.3b; design: plan F7, F9
// (design-director and design-critic, flow-expert). Its sentences were placeholders (R09) until
// the user approved them on 25/10 (T2.3c).
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { openMenu, pick } from "./subject-menu-helpers";

const go = vi.fn();
vi.mock("@/lib/navigate", () => ({ go: (path: string) => go(path) }));

const { SubjectList } = await import("@/components/subjects/subject-list");

const MMT = { id: "3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b", name: "Mạng máy tính", exam_date: "2026-12-15", days_until_exam: 54, has_history: false };
const HDH = { id: "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d", name: "Hệ điều hành", exam_date: "2026-12-20", days_until_exam: 59, has_history: false };
const EXAMPLE = "15/12/2031";
const CONFIRM = "Xóa môn Mạng máy tính? Lịch sử ôn và luyện tập của môn cũng sẽ ẩn theo.";
const DELETED = "Đã xóa môn.";

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
const openEdit = (name: string) => pick("Sửa", name);
// DESIGN-V4: "Sửa" and "Xóa" live in the row's "⋯" menu; the confirmation's own button is "Xóa môn".
const trigger = (name: string) => screen.getByRole("button", { name: `Tùy chọn môn ${name}` });
const deleteButton = (scope: HTMLElement = document.body) => within(scope).getByRole("button", { name: "Xóa môn" });
const keepButton = () => screen.getByRole("button", { name: "Giữ môn" });
const empty204 = () => new Response(null, { status: 204 });

function openConfirm(name: string) {
  return pick("Xóa", name);
}

afterEach(cleanup);
beforeEach(() => go.mockReset());

describe("SubjectList delete (T2.3b, us-01 AC8)", () => {
  it("us-01 AC8: a subject has one \"⋯\" menu holding \"Sửa\" and \"Xóa\", and the edit form has no delete", async () => {
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    await openMenu(MMT.name);
    const names = (await screen.findAllByRole("menuitem")).map((item) => item.getAttribute("aria-label"));
    expect(names).toEqual([`Sửa ${MMT.name}`, `Xóa ${MMT.name}`]);
    // Several rows can be open at once: the subject's name tells the items apart.
    const describedBy = screen.getByRole("menuitem", { name: `Xóa ${MMT.name}` }).getAttribute("aria-describedby") ?? "";
    expect(document.getElementById(describedBy)?.textContent).toBe(MMT.name);
    await act(async () => {
      fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    });
    await openEdit(MMT.name);
    expect(within(row(MMT.name)).queryByRole("button", { name: /^Xóa/ })).toBeNull();
    expect(within(row(MMT.name)).getByRole("button", { name: "Lưu" })).toBeTruthy();
  });

  // Q13 (05/11): a subject with history can be deleted; the confirmation says its history hides too.
  it("us-01 AC8: a subject with history has the same delete button and the history warning in the confirmation", async () => {
    render(<SubjectList subjects={[{ ...MMT, has_history: true }]} example={EXAMPLE} />);
    expect(trigger(MMT.name)).toBeTruthy();
    await openConfirm(MMT.name);
    expect(screen.getByRole("group").textContent).toContain("Lịch sử ôn và luyện tập của môn cũng sẽ ẩn theo.");
  });

  it("us-01 AC8: \"Xóa\" turns the tile into a confirmation in place, focus on \"Giữ môn\"", async () => {
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    await openConfirm(MMT.name);
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
  ])("us-01 AC8: %s goes back to the tile, focus on \"Xóa\"", async (_, keep) => {
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    await openConfirm(MMT.name);
    keep();
    expect(screen.queryByRole("group")).toBeNull();
    expect(document.activeElement).toBe(trigger(MMT.name));
  });

  it("us-01 AC8: deleting sends one DELETE; the row becomes \"Đã xóa môn.\" with no name, focused", async () => {
    const sent = fakeWeb(empty204);
    render(<SubjectList subjects={[MMT, HDH]} example={EXAMPLE} />);
    await openConfirm(MMT.name);
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
    await openConfirm(MMT.name);
    fireEvent.click(deleteButton());
    expect(await screen.findByText(DELETED)).toBeTruthy();
    expect(screen.queryByText("Chưa gửi được. Kiểm tra kết nối rồi thử lại.")).toBeNull();
  });

  it("us-01 AC8: one placeholder at a time; opening \"Sửa\" anywhere clears it", async () => {
    fakeWeb(empty204);
    render(<SubjectList subjects={[MMT, HDH]} example={EXAMPLE} />);
    await openConfirm(MMT.name);
    fireEvent.click(deleteButton());
    await screen.findByText(DELETED);

    await openConfirm(HDH.name);
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
    await openConfirm(MMT.name);
    await openConfirm(HDH.name);
    const [first, second] = screen.getAllByRole("group");
    fireEvent.click(deleteButton(first));
    fireEvent.click(deleteButton(second));
    expect(answers).toHaveLength(2);

    await act(async () => answers[0](empty204()));
    await act(async () => answers[1](empty204()));

    expect(screen.queryByRole("list") && within(screen.getByRole("list")).queryByText(MMT.name)).toBeNull();
    expect(within(screen.getByRole("list")).queryByText(HDH.name)).toBeNull();
    expect(screen.getAllByText(DELETED)).toHaveLength(1);
    expect(within(screen.getByRole("list")).getByText(X.name)).toBeTruthy();
  });

  it("us-01 AC8: deleting the last subject shows the placeholder above the empty state, one \"Tạo môn\"", async () => {
    fakeWeb(empty204);
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    expect(screen.getAllByText("Tạo môn")).toHaveLength(1);
    await openConfirm(MMT.name);
    fireEvent.click(deleteButton());

    const placeholder = await screen.findByText(DELETED);
    expect(screen.getByText("Chưa có môn nào.")).toBeTruthy();
    expect(screen.getAllByText("Tạo môn")).toHaveLength(1);
    expect(placeholder.compareDocumentPosition(screen.getByText("Chưa có môn nào.")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("us-01 AC8: a 409 from an older core is just an error, the confirmation stays", async () => {
    fakeWeb(() => Response.json({ error: "subject_has_history" }, { status: 409 }));
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    await openConfirm(MMT.name);
    fireEvent.click(deleteButton());
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("group")).toBeTruthy();
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
      await openConfirm(MMT.name);
      fireEvent.click(deleteButton());

      expect(await screen.findByText("Chưa gửi được. Kiểm tra kết nối rồi thử lại.")).toBeTruthy();
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
    await openConfirm(MMT.name);
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
    await openConfirm(MMT.name);
    fireEvent.click(deleteButton());
    await waitFor(() => expect(go).toHaveBeenCalledWith("/login"));
  });

  // The user approved the six strings on 25/10 (T2.3c plan G2): none is a placeholder any more.
  it("R09: the approved sentences carry no data-copy=\"tam\" in the page", async () => {
    fakeWeb(empty204);
    render(<SubjectList subjects={[MMT, { ...HDH, has_history: true }]} example={EXAMPLE} />);
    expect(trigger(MMT.name).getAttribute("data-copy")).toBeNull();
    await openConfirm(MMT.name);
    expect(screen.getByText(CONFIRM).getAttribute("data-copy")).toBeNull();
    expect(deleteButton(screen.getByRole("group")).getAttribute("data-copy")).toBeNull();
    expect(keepButton().getAttribute("data-copy")).toBeNull();
    fireEvent.click(deleteButton(screen.getByRole("group")));
    expect((await screen.findByText(DELETED)).getAttribute("data-copy")).toBeNull();
  });
});

describe("SubjectList: no add button while a row is being edited (UI-A, user 05/11)", () => {
  const adds = () => screen.queryAllByText("Tạo môn");
  it("hides \"Tạo môn\" while editing, shows it again after Hủy", async () => {
    render(<SubjectList subjects={[MMT, HDH]} example={EXAMPLE} />);
    expect(adds()).toHaveLength(1);
    await openEdit(MMT.name);
    expect(adds()).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Hủy" }));
    expect(adds()).toHaveLength(1);
  });
  it("Escape leaves the edit mode", async () => {
    render(<SubjectList subjects={[MMT, HDH]} example={EXAMPLE} />);
    await openEdit(MMT.name);
    expect(adds()).toHaveLength(0);
    fireEvent.keyDown(screen.getByRole("button", { name: "Hủy" }), { key: "Escape" });
    expect(adds()).toHaveLength(1);
  });
  it("hides them while a delete is being confirmed too", async () => {
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    await openConfirm(MMT.name);
    expect(adds()).toHaveLength(0);
    fireEvent.click(keepButton());
    expect(adds()).toHaveLength(1);
  });
});

describe("SubjectList \"Đã lưu.\" (T1.20, kept by T2.3b plan F7)", () => {
  it("saving still says \"Đã lưu.\" in the row's status region, which is there before saving", async () => {
    fakeWeb(() => Response.json({ subject: { ...MMT, name: "Mạng" } }));
    render(<SubjectList subjects={[MMT]} example={EXAMPLE} />);
    const region = within(row(MMT.name)).getByRole("status");
    expect(region.textContent).toBe("");
    await openEdit(MMT.name);
    fireEvent.change(screen.getByLabelText("Môn"), { target: { value: "Mạng" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(region.textContent).toBe("Đã lưu."));
  });
});
