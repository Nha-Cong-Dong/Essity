// T4.9 (US-02 AC2): the toc.json reader, against contracts/files/toc.v1.schema.json.
import { describe, expect, it } from "vitest";

import { parseToc, toTree } from "@/lib/toc";

const e = (title: string, level: number, page: number | null) => ({ title, level, page });

describe("parseToc", () => {
  it("accepts the shape of the schema, an empty list too", () => {
    expect(parseToc({ entries: [e("A", 0, 1), e("B", 1, null)] })).toEqual([e("A", 0, 1), e("B", 1, null)]);
    expect(parseToc({ entries: [] })).toEqual([]);
  });

  it.each([
    ["not an object", null],
    ["an array", []],
    ["no entries", {}],
    ["an extra field", { entries: [], x: 1 }],
    ["entries not a list", { entries: "x" }],
    ["a title that is not a string", { entries: [e(1 as never, 0, 1)] }],
    ["a negative level", { entries: [e("A", -1, 1)] }],
    ["a fractional level", { entries: [e("A", 0.5, 1)] }],
    ["page 0", { entries: [e("A", 0, 0)] }],
    ["a missing page", { entries: [{ title: "A", level: 0 }] }],
    ["an extra entry field", { entries: [{ ...e("A", 0, 1), z: 1 }] }],
  ])("refuses %s", (_name, value) => {
    expect(parseToc(value)).toBeNull();
  });
});

describe("toTree", () => {
  it("nests by level and ends a range at the page before the next sibling", () => {
    const tree = toTree([e("C1", 0, 1), e("1.1", 1, 1), e("1.2", 1, 9), e("C2", 0, 25)], 40);
    expect(tree.map((n) => [n.title, n.from, n.to])).toEqual([
      ["C1", 1, 24],
      ["C2", 25, 40],
    ]);
    expect(tree[0].children.map((n) => [n.title, n.from, n.to])).toEqual([
      ["1.1", 1, 8],
      ["1.2", 9, 24],
    ]);
  });

  it("puts an entry whose level jumps under the nearest shallower one", () => {
    const tree = toTree([e("A", 0, 1), e("deep", 3, 2)], null);
    expect(tree[0].children[0].title).toBe("deep");
  });

  it("leaves the range empty for an entry with no page", () => {
    const [node] = toTree([e("A", 0, null)], 10);
    expect([node.from, node.to]).toEqual([null, null]);
  });
});
