// @vitest-environment jsdom
// T7.5a (US-13 AC4, AC5, AC8, AC9; US-01 AC4, AC7): the Đề cương screen and the role picker from
// fixtures. The ARIA tree and its keyboard rules are the risky part (design-decisions.md R1, R2).
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SyllabusScreen } from "@/components/syllabus/syllabus-screen";
import { UploadScreen } from "@/components/syllabus/upload-files";
import { SYLLABUS_STATE_IDS, type SyllabusState, UPLOAD_STATE_IDS } from "@/lib/fixtures/syllabus";

afterEach(cleanup);

const PRIMARY = "[data-variant='primary']";
// DESIGN §4. Only words the app writes are scanned; titles and file names are the user's own.
const FORBIDDEN = /(?<!\p{L})(streak|chuỗi|xếp hạng|ranking|trễ|kém|lười|bỏ lỡ|thất bại|chưa xong|nợ)(?!\p{L})/iu;

function appCopy(container: HTMLElement): string {
  const clone = container.cloneNode(true) as HTMLElement;
  clone.querySelectorAll("[data-user]").forEach((el) => el.remove());
  return clone.textContent ?? "";
}

const item = (container: HTMLElement, id: string) => container.querySelector(`[data-node="${id}"]`) as HTMLElement;
const key = (el: Element, k: string, init: object = {}) => fireEvent.keyDown(el, { key: k, ...init });

describe("every Đề cương state", () => {
  // US-13 AC8, AC9; DESIGN §6.6. Red when: a state has two primaries, or a waiting state has one.
  const NONE: SyllabusState[] = ["loading", "extracting"];
  it.each(SYLLABUS_STATE_IDS)("%s: one primary (none while waiting), no banned word", (state) => {
    const { container } = render(<SyllabusScreen state={state} />);
    expect(container.querySelectorAll(PRIMARY).length).toBe(NONE.includes(state) ? 0 : 1);
    expect(appCopy(container)).not.toMatch(FORBIDDEN);
  });

  // Red when: the primary is not the one the card names for the state.
  it.each([
    ["ready", "Vào buổi học"],
    ["empty-no-main", "Tải giáo trình"],
    ["error", "Thử lại"],
    ["editing", "Lưu"],
    ["range-error", "Lưu"],
    ["save-error", "Lưu"],
  ] as const)("%s: the primary is %s", (state, name) => {
    const { container } = render(<SyllabusScreen state={state} />);
    expect(container.querySelector(PRIMARY)?.textContent).toBe(name);
  });

  // US-13 AC9. Red when: a provisional outline is not labelled as provisional, or the scan has no sentence.
  it("provisional outlines say so in the pencil label and the box", () => {
    const a = render(<SyllabusScreen state="provisional" />);
    expect(a.container.querySelector("[data-main]")?.textContent).toContain("tạm: chia khối 10 trang");
    expect(a.container.querySelector("[data-notice=chunk10]")?.textContent).toContain("Chưa đọc được mục lục. Bạn có thể sửa trực tiếp.");
    cleanup();
    const b = render(<SyllabusScreen state="provisional-scan" />);
    expect(b.container.querySelector("[data-notice=scan]")?.textContent).toContain("ảnh chụp");
  });

  // US-13 AC8. Red when: the empty state offers nothing to do, or invents an outline.
  it("empty-no-main: the sentence, no tree", () => {
    const { container } = render(<SyllabusScreen state="empty-no-main" />);
    expect(container.textContent).toContain("Chưa có đề cương. Tải giáo trình chính để app dựng đề cương.");
    expect(container.querySelector("[role=tree]")).toBeNull();
  });

  // US-13 AC9. Red when: the reading state has a primary or no live text.
  it("extracting: Đang đọc mục lục… in a busy status", () => {
    const { container } = render(<SyllabusScreen state="extracting" />);
    expect(container.querySelector("[role=status][aria-busy=true]")?.textContent).toBe("Đang đọc mục lục…");
  });

  it("error: Thử lại puts focus on the alert block", () => {
    const { container } = render(<SyllabusScreen state="error" />);
    fireEvent.click(screen.getByRole("button", { name: "Thử lại" }));
    expect(document.activeElement).toBe(container.querySelector("[role=alert]"));
  });

  // US-13 AC5. Red when: the totals count an excluded leaf, or a pencil count disagrees with the tree.
  it("ready: totals line counts only leaves not excluded", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    expect(container.querySelector("[data-totals]")?.textContent).toMatch(/^đã học 4\/15 mục · 60\/252 trang$/);
    expect(container.textContent).toContain("1 mục không thi, không tính vào đây.");
  });
});

describe("tree ARIA (US-13 AC4)", () => {
  // Red when: the tree loses its roles, levels or expanded state, or a leaf claims aria-expanded.
  it("role=tree, treeitems with level/size/pos, aria-expanded only on branches, groups only hold treeitems", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    const tree = screen.getByRole("tree");
    expect(tree.getAttribute("aria-label")).toContain("Đề cương");
    const first = item(container, "1");
    expect(first.getAttribute("role")).toBe("treeitem");
    expect(first.getAttribute("aria-level")).toBe("1");
    expect(first.getAttribute("aria-setsize")).toBe("4");
    expect(first.getAttribute("aria-posinset")).toBe("1");
    expect(first.getAttribute("aria-expanded")).toBe("false");
    const leaf = item(container, "2.1");
    expect(leaf.getAttribute("aria-level")).toBe("2");
    expect(leaf.hasAttribute("aria-expanded")).toBe(false);
    for (const group of container.querySelectorAll("[role=group]")) {
      expect([...group.children].every((c) => c.getAttribute("role") === "treeitem")).toBe(true);
    }
  });

  // Red when: the name carries the status again (it is a description), or the hint is missing.
  it("name is title + range; the status is the description; a leaf hints Enter to edit", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    const leaf = item(container, "2.2");
    const name = leaf
      .getAttribute("aria-labelledby")!
      .split(" ")
      .map((id) => document.getElementById(id)!.textContent)
      .join(", ");
    expect(name).toBe("2.2 Web và HTTP, tr. 55–68");
    const described = leaf
      .getAttribute("aria-describedby")!
      .split(" ")
      .map((id) => document.getElementById(id)!.textContent);
    expect(described).toEqual(["đã học tr. 55–60 trong tr. 55–68", "Nhấn Enter để sửa"]);
    const branch = item(container, "2");
    const hint = document.getElementById(branch.getAttribute("aria-describedby")!.split(" ")[1])!.textContent;
    expect(hint).toBe("Nhấn Enter để mở hoặc đóng nhánh");
  });

  // US-13 AC4 (keyboard). Red when: Tab can land on more than one row, or the roving index is lost.
  it("one tab stop: exactly one treeitem has tabindex 0, and it follows focus", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    const stops = () => [...container.querySelectorAll("[role=treeitem]")].filter((e) => e.getAttribute("tabindex") === "0");
    expect(stops().length).toBe(1);
    const first = stops()[0] as HTMLElement;
    key(first, "ArrowDown");
    expect(stops().length).toBe(1);
    expect(stops()[0]).not.toBe(first);
  });

  // US-13 AC4. Red when: the status line says "chưa học" in a warning way, or a mark is only colour.
  it("studied and partial rows carry their status as words; a branch with nothing countable has no tick", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    fireEvent.click(item(container, "1").querySelector("[data-row]")!);
    expect(item(container, "1.1").textContent).toContain("đã học");
    expect(item(container, "1.1").querySelector("svg")).not.toBeNull();
    expect(container.querySelectorAll("[data-status=none] .text-partial, [data-status=none] .text-miss").length).toBe(0);
  });
});

describe("tree keyboard", () => {
  it("→ opens a branch, → again enters it, ← goes back to the branch, ← folds it", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    const one = item(container, "1");
    one.focus();
    key(one, "ArrowRight");
    expect(one.getAttribute("aria-expanded")).toBe("true");
    key(one, "ArrowRight");
    expect(document.activeElement).toBe(item(container, "1.1"));
    key(item(container, "1.1"), "ArrowLeft");
    expect(document.activeElement).toBe(one);
    key(one, "ArrowLeft");
    expect(one.getAttribute("aria-expanded")).toBe("false");
  });

  it("Home and End go to the first and last visible row", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    const first = item(container, "1");
    first.focus();
    key(first, "End");
    const rows = [...container.querySelectorAll("[role=treeitem]")].filter((e) => !e.parentElement?.closest("li")?.hasAttribute("hidden"));
    expect(document.activeElement).toBe(rows[rows.length - 1]);
    key(document.activeElement!, "Home");
    expect(document.activeElement).toBe(first);
  });

  // Red when: Enter on a branch opens the panel instead of folding (the two meanings are split).
  it("Enter on a branch folds it and opens no panel", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    const four = item(container, "4");
    four.focus();
    key(four, "Enter");
    expect(four.getAttribute("aria-expanded")).toBe("true");
    expect(container.querySelector("[data-panel]")).toBeNull();
    key(four, "Enter");
    expect(four.getAttribute("aria-expanded")).toBe("false");
  });

  // Red when: Enter on a leaf does not open the panel with focus on its first button, or Esc loses the row.
  it("Enter on a leaf opens the panel and focuses its first button; Esc closes it and returns to the row", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    const leaf = item(container, "2.3");
    leaf.focus();
    key(leaf, "Enter");
    const panel = container.querySelector("[data-panel='2.3']") as HTMLElement;
    expect(panel).not.toBeNull();
    expect(document.activeElement).toBe(within(panel).getAllByRole("button")[0]);
    key(document.activeElement!, "Escape");
    expect(container.querySelector("[data-panel]")).toBeNull();
    expect(document.activeElement).toBe(leaf);
  });

  // Red when: a branch can only be edited by mouse (the ⋯ button is not reachable by Tab from its row).
  it("the ⋯ button is a real button, reachable only from the row that has the focus", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    const active = [...container.querySelectorAll("[role=treeitem]")].find((e) => e.getAttribute("tabindex") === "0")!;
    expect(active.querySelector("[data-more]")?.getAttribute("tabindex")).toBe("0");
    const other = item(container, "4");
    expect(other.querySelector("[data-more]")?.getAttribute("tabindex")).toBe("-1");
    expect(active.querySelector("[data-more]")?.tagName).toBe("BUTTON");
    expect(active.querySelector("[data-more]")?.getAttribute("aria-hidden")).toBeNull();
  });

  it("Shift+F10 and the Menu key open the panel on any row, a branch included", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    const four = item(container, "4");
    four.focus();
    key(four, "F10", { shiftKey: true });
    expect(container.querySelector("[data-panel='4']")).not.toBeNull();
    key(document.activeElement!, "Escape");
    key(four, "ContextMenu");
    expect(container.querySelector("[data-panel='4']")).not.toBeNull();
  });

  // Red when: folding a branch that holds the focus leaves focus on a row that is gone.
  it("folding a branch that holds the focus moves focus up to the branch", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    const two = item(container, "2");
    expect(two.getAttribute("aria-expanded")).toBe("true");
    const inside = item(container, "2.1");
    act(() => inside.focus());
    fireEvent.click(two.querySelector("[data-chevron]")!);
    expect(two.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(two);
  });

  // Red when: typing in a panel field moves the tree focus (keys bubble up from the input).
  it("arrow keys typed in a panel field do not move the tree", () => {
    const { container } = render(<SyllabusScreen state="editing" />);
    const input = screen.getByLabelText("Từ trang");
    input.focus();
    key(input, "ArrowDown");
    expect(document.activeElement).toBe(input);
    expect(container.querySelector("[data-panel]")).not.toBeNull();
  });
});

describe("panel actions (US-13 AC4, AC5, AC6)", () => {
  const panelOf = (container: HTMLElement, id: string) => within(container.querySelector(`[data-panel='${id}']`) as HTMLElement);

  // Red when: a leaf's panel has other than three buttons, or labels do not name the section.
  it("a leaf's panel has three quiet buttons, each named with the section", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    const leaf = item(container, "2.3");
    leaf.focus();
    key(leaf, "Enter");
    const buttons = panelOf(container, "2.3").getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual([
      "Sửa khoảng trang 2.3 Thư điện tử trên Internet",
      "Đánh dấu đã học 2.3 Thư điện tử trên Internet",
      "Bỏ khỏi đề cương thi 2.3 Thư điện tử trên Internet",
    ]);
    expect(container.querySelector("[role=group] [role=group][data-panel]")).toBeNull();
    expect(container.querySelector("[data-panel]")?.getAttribute("role")).toBeNull();
  });

  // Red when: a branch panel has more than four buttons, or shows a button with a count of 0.
  it("a branch panel shows up to four buttons and hides a mark button with nothing to change", () => {
    const { container } = render(<SyllabusScreen state="parent-panel" />);
    const names = panelOf(container, "2").getAllByRole("button").map((b) => b.textContent);
    expect(names.length).toBeLessThanOrEqual(4);
    expect(names[0]).toContain("Sửa khoảng trang");
    expect(names.some((n) => n?.includes("Đánh dấu 2 mục chưa học là đã học"))).toBe(true);
    expect(names.some((n) => n?.includes("là chưa học"))).toBe(false);
    expect(names[names.length - 1]).toContain("Bỏ khỏi đề cương thi");
  });

  // Red when: marking changes the label but the totals stay, or focus is lost after the action.
  it("marking a leaf updates totals, flips the label, keeps focus on the button and says so in the status", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    const leaf = item(container, "2.3");
    leaf.focus();
    key(leaf, "Enter");
    fireEvent.click(panelOf(container, "2.3").getByRole("button", { name: /^Đánh dấu đã học/ }));
    expect(container.querySelector("[data-totals]")?.textContent).toMatch(/^đã học 5\/15 mục/);
    expect(panelOf(container, "2.3").getByRole("button", { name: /^Đánh dấu chưa học/ })).toBeTruthy();
    expect(container.querySelector("[data-live]")?.textContent).toBe("Đã đánh dấu đã học.");
  });

  // Red when: after the last unstudied child is marked, focus drops to the page because the button vanished.
  it("a branch mark button that vanishes after its own action leaves focus on another button of the panel", async () => {
    const { container } = render(<SyllabusScreen state="parent-panel" />);
    const button = panelOf(container, "2").getByRole("button", { name: /^Đánh dấu 2 mục chưa học là đã học/ });
    button.focus();
    fireEvent.click(button);
    await waitFor(() => expect(container.querySelector("[data-panel='2']")?.contains(document.activeElement)).toBe(true));
  });

  // Red when: Bỏ keeps the leaf in the totals, or Đưa lại does not offer itself.
  it("Bỏ khỏi đề cương thi removes the leaf from the totals and flips to Đưa lại", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    const leaf = item(container, "2.3");
    leaf.focus();
    key(leaf, "Enter");
    fireEvent.click(panelOf(container, "2.3").getByRole("button", { name: /^Bỏ khỏi đề cương thi/ }));
    expect(container.querySelector("[data-totals]")?.textContent).toMatch(/^đã học 4\/14 mục/);
    expect(item(container, "2.3").textContent).toContain("không thi");
    expect(panelOf(container, "2.3").getByRole("button", { name: /^Đưa lại/ })).toBeTruthy();
  });
});

describe("edit range (US-13 AC4)", () => {
  // Red when: Lưu keeps an overlapping range, or the error is only colour / not tied to the field.
  it("range-error: the field is aria-invalid, tied to a sentence, and Lưu stays pressable", () => {
    const { container } = render(<SyllabusScreen state="range-error" />);
    const from = screen.getByLabelText("Từ trang");
    expect(from.getAttribute("aria-invalid")).toBe("true");
    const text = document.getElementById(from.getAttribute("aria-describedby")!)!.textContent;
    expect(text).toMatch(/^Khoảng này chồng lên mục 2\.2 \(tr\. 55–68\)\.$/);
    expect((screen.getByRole("button", { name: "Lưu" }) as HTMLButtonElement).disabled).toBe(false);
    expect(container.querySelector("[data-panel]")).not.toBeNull();
  });

  // Red when: a bad range is saved, or the first wrong field does not get focus.
  it("saving a bad range shows the sentence and focuses the field", async () => {
    render(<SyllabusScreen state="editing" />);
    const from = screen.getByLabelText("Từ trang") as HTMLInputElement;
    fireEvent.change(from, { target: { value: "900" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(document.getElementById(from.getAttribute("aria-describedby")!)?.textContent).toBe("Trang bắt đầu phải nhỏ hơn hoặc bằng trang kết thúc.");
    await waitFor(() => expect(document.activeElement).toBe(from));
  });

  // Red when: a valid save leaves the panel open, loses focus, or does not mark the source as edited.
  it("a valid range saves, closes the panel, returns focus to the row and the source says 'bạn đã sửa'", () => {
    const { container } = render(<SyllabusScreen state="editing" />);
    fireEvent.change(screen.getByLabelText("Đến trang"), { target: { value: "77" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(container.querySelector("[data-panel]")).toBeNull();
    expect(document.activeElement).toBe(item(container, "2.3"));
    expect(container.querySelector("[data-live]")?.textContent).toBe("Đã lưu: mục 2.3 tr. 69–77.");
    expect(container.querySelector("[data-main]")?.textContent).toContain("bạn đã sửa");
  });

  // Red when: Esc inside the form drops the learner out of the panel instead of back to its buttons.
  it("Hủy goes back to the buttons with focus on Sửa khoảng trang; Esc does the same", async () => {
    const { container } = render(<SyllabusScreen state="editing" />);
    fireEvent.click(screen.getByRole("button", { name: "Hủy" }));
    await waitFor(() => expect(document.activeElement?.textContent).toContain("Sửa khoảng trang"));
    expect(container.querySelector("[data-panel]")).not.toBeNull();
  });

  // Red when: slides are called pages.
  it("flat-pptx speaks of slides", () => {
    const { container } = render(<SyllabusScreen state="flat-pptx" />);
    expect(container.querySelector("[data-totals]")?.textContent).toMatch(/slide$/);
    expect(item(container, "s1").textContent).toContain("slide 1");
  });

  // Red when: a network failure on save is silent, or loses the numbers typed.
  it("save-error: an alert with Thử lại and the typed numbers kept", () => {
    render(<SyllabusScreen state="save-error" />);
    expect(screen.getByRole("alert").textContent).toContain("Chưa lưu được. Thử lại.");
    expect((screen.getByLabelText("Đến trang") as HTMLInputElement).value).toBe("80");
  });
});

describe("states of the upload form", () => {
  // US-01 AC4, AC7. Red when: a state has two primaries, or an empty one has none.
  it.each(UPLOAD_STATE_IDS)("%s: one primary, no banned word", (state) => {
    const { container } = render(<UploadScreen state={state} />);
    expect(container.querySelectorAll(PRIMARY).length).toBe(1);
    expect(appCopy(container)).not.toMatch(FORBIDDEN);
  });

  // Red when: renaming a file leaves two primaries (Lưu and Vào môn học).
  it.each([
    ["upload-empty", "Tải tài liệu lên"],
    ["upload-files", "Vào môn học"],
    ["upload-rename", "Lưu"],
    ["upload-uploading", "Vào môn học"],
  ] as const)("%s: the primary is %s", (state, name) => {
    const { container } = render(<UploadScreen state={state} />);
    expect(container.querySelector(PRIMARY)?.textContent).toBe(name);
  });
});

describe("role picker (US-01 AC4)", () => {
  const group = (name: string) => screen.getByRole("radiogroup", { name: `Vai trò của ${name}` });

  // Red when: a file has no role selected, or two pills of one file are checked.
  it("each file has three exclusive pills; the default rule gave the first PDF the main role", () => {
    render(<UploadScreen state="upload-files" />);
    const radios = within(group("Giáo trình Mạng máy tính")).getAllByRole("radio");
    expect(radios.map((r) => (r as HTMLInputElement).checked)).toEqual([true, false, false]);
    expect(within(group("Slide tuần 1-6")).getAllByRole("radio").filter((r) => (r as HTMLInputElement).checked).length).toBe(1);
  });

  // Red when: a picture can become the main syllabus, or the reason is only a tooltip.
  it("an image cannot be main: the pill is disabled (skipped by the arrows) and the sentence is visible", () => {
    render(<UploadScreen state="upload-files" />);
    const main = within(group("Ảnh vở chương 2")).getByRole("radio", { name: "Giáo trình chính" }) as HTMLInputElement;
    expect(main.disabled).toBe(true);
    expect(screen.getByText("Ảnh chưa dựng được đề cương.")).toBeTruthy();
  });

  // Red when: the meaning line does not follow the chosen role, or is not tied to the group.
  it("the meaning line follows the role and the group is described by it", () => {
    render(<UploadScreen state="upload-files" />);
    const g = group("Đề thi các năm");
    expect(document.getElementById(g.getAttribute("aria-describedby")!)?.textContent).toBe("App tách câu hỏi và gợi ý dạng câu.");
  });

  // Red when: choosing Giáo trình chính for a second file makes two mains, or asks nothing when the old one is established.
  it("choosing main when one is established asks once, without a dialog; Giữ nguyên changes nothing", () => {
    const { container } = render(<UploadScreen state="upload-main-exists" />);
    const box = container.querySelector("[data-swap]") as HTMLElement;
    expect(box.textContent).toContain("Môn này đã có giáo trình chính:");
    expect(container.querySelector("dialog, [role=dialog], [role=alertdialog]")).toBeNull();
    fireEvent.click(within(box).getByRole("button", { name: "Giữ nguyên" }));
    expect(container.querySelector("[data-swap]")).toBeNull();
    const main = within(group("Giáo trình bản mới")).getByRole("radio", { name: "Giáo trình chính" }) as HTMLInputElement;
    expect(main.checked).toBe(false);
  });

  it("Đổi sang file này makes this file the main one and says so", () => {
    const { container } = render(<UploadScreen state="upload-main-exists" />);
    fireEvent.click(screen.getByRole("button", { name: "Đổi sang file này" }));
    const main = within(group("Giáo trình bản mới")).getByRole("radio", { name: "Giáo trình chính" }) as HTMLInputElement;
    expect(main.checked).toBe(true);
    expect(container.querySelector("[data-live]")?.textContent).toBe("Giáo trình chính giờ là Giáo trình bản mới.");
  });

  // Red when: a main that is only the batch default makes the learner confirm for nothing.
  it("a main that is only the batch default swaps straight away", () => {
    const { container } = render(<UploadScreen state="upload-files" />);
    fireEvent.click(within(group("Slide tuần 1-6")).getByRole("radio", { name: "Giáo trình chính" }));
    expect(container.querySelector("[data-swap]")).toBeNull();
    expect((within(group("Slide tuần 1-6")).getByRole("radio", { name: "Giáo trình chính" }) as HTMLInputElement).checked).toBe(true);
    expect((within(group("Giáo trình Mạng máy tính")).getByRole("radio", { name: "Tài liệu phụ" }) as HTMLInputElement).checked).toBe(true);
    expect(container.querySelector("[data-live]")?.textContent).toBe("Giáo trình chính giờ là Slide tuần 1-6.");
  });

  // US-01 AC7. Red when: a duplicate name is saved.
  it("upload-rename: a duplicate short name is refused with a sentence that says what to do", () => {
    render(<UploadScreen state="upload-rename" />);
    const input = screen.getByRole("textbox") as HTMLInputElement;
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(document.getElementById(input.getAttribute("aria-describedby")!)?.textContent).toBe("Đã có tài liệu tên “Slide tuần 1-6”. Đặt tên khác, ví dụ “Slide tuần 1-6 2”.");
  });

  it("a new name saves, focus returns to the pencil, and the status says so", async () => {
    const { container } = render(<UploadScreen state="upload-rename" />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Slide tuần 7-12" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(container.querySelector("[data-live]")?.textContent).toBe("Đã đổi tên thành Slide tuần 7-12.");
    await waitFor(() => expect(document.activeElement?.getAttribute("aria-label")).toBe("Sửa tên Slide tuần 7-12"));
  });

  // Red when: refusals are one alert each (a screen reader is cut off by the next one), or become file rows.
  it("upload-rejected: one grouped alert region; refused files are not rows", () => {
    const { container } = render(<UploadScreen state="upload-rejected" />);
    expect(container.querySelectorAll("[role=alert]").length).toBe(1);
    expect(container.querySelector("[role=alert]")?.textContent).toContain("App nhận PDF, DOCX, PPTX, JPG và PNG.");
    expect(container.querySelector("[role=alert]")?.textContent).toContain("lớn quá. Chia nhỏ rồi tải lại.");
    expect(container.querySelectorAll("li[data-file]").length).toBe(3);
    expect(container.textContent).toContain("Không đọc được 3 trang (tr. 12, 13, 40)");
  });

  // Red when: Vào môn học is blocked while files are still uploading (a slow network traps the learner).
  it("upload-uploading: Vào môn học is a live link and the note says the rest continues in the background", () => {
    const { container } = render(<UploadScreen state="upload-uploading" />);
    const link = screen.getByRole("link", { name: "Vào môn học" });
    expect(link.getAttribute("aria-disabled")).not.toBe("true");
    expect(container.textContent).toContain("Còn 2 file đang tải, vẫn tải tiếp ở nền.");
    expect(link.getAttribute("aria-describedby")).toBe("uploading-note");
  });
});
