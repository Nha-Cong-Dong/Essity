import { describe, expect, it } from "vitest";

import { matchBoxes } from "@/components/vault/pdf-page";

const box = (left: number) => ({ left, top: 0, width: 10, height: 10 });

describe("G4 matchBoxes", () => {
  // Red when: a passage split over text runs, or with other whitespace, is not found.
  it("marks every run the passage touches, ignoring whitespace and case", () => {
    const items = [
      { str: "TCP dùng bắt", box: box(0) },
      { str: "tay ba  bước", box: box(20) },
      { str: "để nối", box: box(40) },
    ];
    expect(matchBoxes(items, "bắt tay ba bước")).toEqual([box(0), box(20)]);
  });

  it("finds nothing when the passage is not on the page", () => {
    expect(matchBoxes([{ str: "abc", box: box(0) }], "xyz")).toEqual([]);
  });
});
