// T7.5 (US-13 AC4-AC6, AC9; US-01 AC5): the outline API mapped to the tree, and the change list.
import { describe, expect, it } from "vitest";

import { diffChanges, type OutlineOut, outlineView } from "@/lib/syllabus/api";
import { applyMark, applyRange, excludeToggle } from "@/lib/syllabus/tree";

type Section = OutlineOut["sections"][number];
const sec = (over: Partial<Section> & { id: string }): Section => ({
  parent_id: null, title: over.id, first_page: 1, last_page: 10, weight: 10, unit: "page", source: "bookmark",
  excluded: false, excluded_effective: false, progress: 0, studied: false, children: [], ...over,
});
const out = (sections: Section[], over: Partial<OutlineOut> = {}): OutlineOut => ({
  subject_id: "s", document: { id: "d", page_count: 100, short_name: "Giáo trình" }, progress: 0, reason: null,
  temporary: false, sections, ...over,
});
const view = (o: OutlineOut) => {
  const v = outlineView(o);
  if (v.kind !== "ready") throw new Error("not ready");
  return v;
};

describe("outlineView", () => {
  it("US-13 AC4: maps ranges, studied and partly studied leaves, and the learner's own edits", () => {
    const v = view(out([
      sec({ id: "1", last_page: 30, weight: 30, children: [
        sec({ id: "1.1", studied: true, progress: 1, source: "user" }),
        sec({ id: "1.2", first_page: 11, last_page: 20, progress: 0.5 }),
        sec({ id: "1.3", first_page: 21, last_page: 30 }),
      ] }),
    ]));
    const [a, b, c] = v.nodes[0]!.children;
    expect(a).toMatchObject({ done: true, byHand: true, part: null, edited: true });
    expect(b).toMatchObject({ done: false, part: [11, 15], edited: false });
    expect(c).toMatchObject({ done: false, part: null, from: 21, to: 30 });
    expect(v.total).toBe(100);
  });

  it("US-13 AC9: only chunk10 sections make the outline temporary", () => {
    const v = view(out([sec({ id: "1", source: "chunk10" })], { temporary: true }));
    expect(v).toMatchObject({ temporary: true, source: "chunk10" });
    expect(view(out([sec({ id: "1" })])).temporary).toBe(false);
  });

  it("US-13 AC1: no textbook, not indexed and no outline are told apart", () => {
    expect(outlineView(out([], { document: null, reason: "no_textbook" }))).toMatchObject({ reason: "no_textbook" });
    expect(outlineView(out([], { reason: "not_indexed" }))).toMatchObject({ reason: "not_indexed", name: "Giáo trình" });
    expect(outlineView(out([]))).toMatchObject({ reason: "no_outline" });
  });
});

describe("diffChanges", () => {
  const nodes = view(out([sec({ id: "1", last_page: 20, weight: 20, children: [
    sec({ id: "1.1", last_page: 10 }), sec({ id: "1.2", first_page: 11, last_page: 20 }),
  ] })])).nodes;

  it("US-13 AC4: a range edit is one PATCH with both ends", () => {
    expect(diffChanges(nodes, applyRange(nodes, "1.1", 2, 8))).toEqual([{ id: "1.1", body: { first_page: 2, last_page: 8 } }]);
  });

  it("US-13 AC4: marking a leaf, and a branch (its leaves), are studied PATCHes", () => {
    expect(diffChanges(nodes, applyMark(nodes, "1.2", true))).toEqual([{ id: "1.2", body: { studied: true } }]);
    expect(diffChanges(nodes, applyMark(nodes, "1", true)).map((c) => c.id)).toEqual(["1.1", "1.2"]);
  });

  it("US-13 AC6: excluding is one PATCH on that node; nothing changed is nothing", () => {
    expect(diffChanges(nodes, excludeToggle(nodes, "1"))).toEqual([{ id: "1", body: { excluded: true } }]);
    expect(diffChanges(nodes, nodes)).toEqual([]);
  });
});
