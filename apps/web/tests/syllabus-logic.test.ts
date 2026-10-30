// T7.5a (US-13 AC4, AC5, AC6; US-01 AC4, AC7; DESIGN §6.4, §6.6): the pure rules of the syllabus
// screen and the role picker.
import { describe, expect, it } from "vitest";

import { defaultRole, ROLE_HINT, switchMain, type UploadFile } from "@/lib/syllabus/roles";
import {
  applyMark,
  applyRange,
  countCountable,
  describeNode,
  excludeToggle,
  findNode,
  markCounts,
  nodeStatus,
  progress,
  rangeText,
  sourceLabel,
  type SyllabusNode,
  validateRange,
  visibleRows,
} from "@/lib/syllabus/tree";

const leaf = (id: string, from: number, to: number, extra: Partial<SyllabusNode> = {}): SyllabusNode => ({
  id,
  title: `Mục ${id}`,
  from,
  to,
  weight: to - from + 1,
  excluded: false,
  done: false,
  part: null,
  byHand: false,
  edited: false,
  children: [],
  ...extra,
});
const branch = (id: string, from: number, to: number, children: SyllabusNode[]): SyllabusNode => ({
  ...leaf(id, from, to),
  children,
});

const tree = (): SyllabusNode[] => [
  branch("1", 1, 20, [leaf("1.1", 1, 10, { done: true }), leaf("1.2", 11, 20, { part: [11, 14] })]),
  branch("2", 21, 40, [leaf("2.1", 21, 30), leaf("2.2", 31, 40, { excluded: true })]),
];

describe("progress (US-13 AC5)", () => {
  // Red when: a leaf under an excluded branch, or an excluded leaf, is counted in the total.
  it("counts leaves not excluded; an excluded leaf or branch drops out of both sides", () => {
    expect(progress(tree())).toEqual({ done: 1, total: 3, pagesDone: 14, pagesTotal: 30, excluded: 1 });
    const t = tree();
    t[0].excluded = true;
    expect(progress(t)).toEqual({ done: 0, total: 1, pagesDone: 0, pagesTotal: 10, excluded: 3 });
  });
  // Red when: a partly studied leaf counts as done, or its pages are ignored (US-13 AC6).
  it("a partly studied leaf adds its covered pages, not a done mark", () => {
    const p = progress([leaf("a", 1, 10, { part: [1, 5] })]);
    expect(p.done).toBe(0);
    expect(p.pagesDone).toBe(5);
  });
  it("countCountable is the one denominator parents, buttons and status share", () => {
    expect(countCountable(tree()[0])).toBe(2);
    expect(countCountable(tree()[1])).toBe(1);
  });
});

describe("node status", () => {
  it("leaf: none, partial, done", () => {
    expect(nodeStatus(leaf("a", 1, 5))).toBe("none");
    expect(nodeStatus(leaf("a", 1, 5, { part: [1, 2] }))).toBe("partial");
    expect(nodeStatus(leaf("a", 1, 5, { done: true }))).toBe("done");
  });
  // Red when: a branch shows a tick while a countable leaf is still open, or with nothing to count.
  it("branch is done only when every countable leaf is done and there is at least one", () => {
    expect(nodeStatus(tree()[0])).toBe("partial");
    const t = tree();
    t[1].children[0].done = true;
    expect(nodeStatus(t[1])).toBe("done");
    t[1].children[0].excluded = true;
    expect(nodeStatus(t[1])).toBe("empty");
  });
});

describe("marking (US-13 AC4, AC6)", () => {
  // Red when: marking a chapter as studied overwrites a leaf the learner declared partly or fully.
  it("marking a branch studied only changes leaves with nothing studied", () => {
    const t = tree();
    expect(markCounts(findNode(t, "1")!)).toEqual({ toStudied: 0, toUnstudied: 0 });
    expect(findNode(applyMark(t, "1", true), "1.2")).toMatchObject({ done: false, part: [11, 14] });
    expect(markCounts(findNode(t, "2")!)).toEqual({ toStudied: 1, toUnstudied: 0 });
    expect(findNode(applyMark(t, "2", true), "2.1")).toMatchObject({ done: true, byHand: true });
  });
  // Red when: "chưa học" on a chapter erases a range the learner declared when logging a session.
  it("marking a branch unstudied only undoes leaves marked by hand", () => {
    const marked = applyMark(tree(), "2", true);
    expect(markCounts(findNode(marked, "2")!)).toEqual({ toStudied: 0, toUnstudied: 1 });
    expect(findNode(applyMark(marked, "2", false), "2.1")).toMatchObject({ done: false, byHand: false });
    expect(findNode(applyMark(tree(), "1", false), "1.1")!.done).toBe(true);
  });
  it("a leaf toggles both ways and a partly studied leaf can be completed", () => {
    const on = applyMark(tree(), "2.1", true);
    expect(findNode(on, "2.1")!.done).toBe(true);
    expect(findNode(applyMark(on, "2.1", false), "2.1")!.done).toBe(false);
    expect(findNode(applyMark(tree(), "1.2", true), "1.2")).toMatchObject({ done: true, part: null });
  });
  it("excluded leaves are not marked", () => {
    expect(findNode(applyMark(tree(), "2", true), "2.2")!.done).toBe(false);
  });
});

describe("exclude (US-13 AC5)", () => {
  // Red when: bringing a branch back also brings back a child the learner dropped on its own.
  it("Đưa lại on a branch keeps a child dropped separately", () => {
    let t = excludeToggle(tree(), "2.1");
    t = excludeToggle(t, "2");
    t = excludeToggle(t, "2");
    expect(findNode(t, "2.1")!.excluded).toBe(true);
    expect(progress(t).total).toBe(2);
  });
});

describe("range (US-13 AC4)", () => {
  const ctx = { total: 820, parent: [45, 98] as [number, number], siblings: [{ label: "3.3", from: 59, to: 64 }] };
  it.each([
    [60, 50, "Trang bắt đầu phải nhỏ hơn hoặc bằng trang kết thúc."],
    [50, 900, "Giáo trình chỉ có 820 trang."],
    [10, 20, "Khoảng này nằm ngoài mục cha (tr. 45–98)."],
    [58, 60, "Khoảng này chồng lên mục 3.3 (tr. 59–64)."],
  ])("%i-%i is refused: %s", (from, to, message) => {
    expect(validateRange(from, to, ctx, "page")).toBe(message);
  });
  it("accepts a range inside its parent and clear of its neighbours", () => {
    expect(validateRange(52, 58, ctx, "page")).toBeNull();
    expect(validateRange(52, 52, ctx, "page")).toBeNull();
  });
  it.each([NaN, 0, -3, 1.5])("%s is not a page", (n) => {
    expect(validateRange(n, 5, ctx, "page")).toBe("Nhập số trang, ví dụ 52.");
  });
  // Red when: a saved range keeps the old weight, or the node is not marked as user-edited.
  it("applyRange rewrites the range and weight and marks the node as user-edited", () => {
    const next = applyRange(tree(), "2.1", 21, 25);
    expect(findNode(next, "2.1")).toMatchObject({ from: 21, to: 25, weight: 5, edited: true });
  });
});

describe("labels", () => {
  it("source labels", () => {
    expect(sourceLabel("bookmark", false)).toBe("từ bookmark");
    expect(sourceLabel("heading", false)).toBe("từ heading");
    expect(sourceLabel("llm_toc", false)).toBe("từ mục lục (AI đọc)");
    expect(sourceLabel("chunk10", false)).toBe("tạm: chia khối 10 trang");
    expect(sourceLabel("bookmark", true)).toBe("bạn đã sửa");
  });
  it("rangeText follows the unit", () => {
    expect(rangeText(52, 58, "page")).toBe("tr. 52–58");
    expect(rangeText(52, 52, "page")).toBe("tr. 52");
    expect(rangeText(4, 9, "slide")).toBe("slide 4–9");
  });
  it("describeNode: leaf and branch", () => {
    const t = tree();
    expect(describeNode(findNode(t, "1.2")!, "page")).toBe("đã học tr. 11–14 trong tr. 11–20");
    expect(describeNode(findNode(t, "2.2")!, "page")).toBe("không thi");
    expect(describeNode(t[0], "page")).toBe("2 mục, đã học 1/2 mục");
  });
});

describe("visible rows", () => {
  it("lists a branch's children only while it is open, with level and position", () => {
    const rows = visibleRows(tree(), new Set(["1"]));
    expect(rows.map((r) => r.node.id)).toEqual(["1", "1.1", "1.2", "2"]);
    expect(rows[1]).toMatchObject({ level: 2, setSize: 2, posInSet: 1, parentId: "1" });
  });
});

describe("role picker rules (US-01 AC4, AC7; DESIGN §6.4)", () => {
  const f = (id: string, kind: UploadFile["kind"], role: UploadFile["role"] = "supplementary"): UploadFile => ({
    id,
    name: id,
    kind,
    role,
    state: "ready",
  });
  // Red when: a second main appears for a subject, or an image becomes the main one.
  it("the first PDF/DOCX/PPTX is the main one when the subject has none; the rest are supplementary", () => {
    expect(defaultRole(f("a", "pdf"), { subjectHasMain: false, batch: [] })).toBe("main");
    expect(defaultRole(f("b", "pptx"), { subjectHasMain: false, batch: [f("a", "pdf", "main")] })).toBe("supplementary");
  });
  it("a subject that already has a main, or an image, defaults to supplementary", () => {
    expect(defaultRole(f("a", "pdf"), { subjectHasMain: true, batch: [] })).toBe("supplementary");
    expect(defaultRole(f("a", "image"), { subjectHasMain: false, batch: [] })).toBe("supplementary");
  });
  // Red when: a bank is guessed from a file name.
  it("never guesses the question bank", () => {
    expect(defaultRole(f("de-thi-2024.pdf", "pdf"), { subjectHasMain: true, batch: [] })).toBe("supplementary");
  });
  it("has one meaning line per role", () => {
    expect(Object.keys(ROLE_HINT).sort()).toEqual(["bank", "main", "supplementary"]);
  });
  // Red when: one main is kept in two files after a swap.
  it("switchMain swaps directly: the old main falls back to supplementary", () => {
    const files = [f("a", "pdf", "main"), f("b", "pdf")];
    expect(switchMain(files, "b").map((x) => x.role)).toEqual(["supplementary", "main"]);
  });
});
