// T9.3a (US-18 AC1, AC3, AC4, AC5; DESIGN §6.14): the pure parts of the command bar: the summary
// sentence, name cutting, the length rule, and the link built from {kind, id}.
import { describe, expect, it } from "vitest";

import {
  COMMAND_MAX,
  commandLength,
  linkFor,
  normalizeCommand,
  summarize,
  tooLong,
  truncateName,
} from "@/components/command/logic";

const ID = "0b8f1d2e-0000-4000-8000-000000000001";

describe("summarize", () => {
  // US-18 AC4. Red when: a command touching 2 or more items does not say how many.
  it("AC4: the count is inside the sentence when N > 1, and absent when N = 1", () => {
    expect(summarize({ verb: "bỏ", noun: "mục", tail: "khỏi đề cương thi", scope: "chương 7", count: 9 })).toBe(
      "bỏ 9 mục khỏi đề cương thi (chương 7)",
    );
    expect(summarize({ verb: "sửa", noun: "thẻ", target: "TCP", count: 1 })).toBe("sửa thẻ TCP");
  });

  // US-18 AC4. Red when: 11 items show no "11".
  it("AC4: 11 items put 11 in the sentence", () => {
    expect(summarize({ verb: "đánh dấu đã học", noun: "mục", count: 11 })).toContain("11");
  });

  // Red when: a long name pushes the number out, or the number is cut.
  it("cuts names, never numbers", () => {
    const long = "x".repeat(200);
    const text = summarize({ verb: "sửa", noun: "thẻ", target: long, count: 1250 });
    expect(text).toContain("1250");
    expect([...text].length).toBeLessThan(90);
    expect(text).toContain("…");
  });
});

describe("truncateName", () => {
  it("leaves a name up to 60 characters alone and cuts a longer one to 60 with an ellipsis", () => {
    expect(truncateName("a".repeat(60))).toBe("a".repeat(60));
    const cut = truncateName("a".repeat(61));
    expect([...cut].length).toBe(60);
    expect(cut.endsWith("…")).toBe(true);
  });

  // Red when: a cut lands inside an emoji and leaves half of a surrogate pair.
  it("cuts by code points", () => {
    expect(truncateName("😀".repeat(70))).toBe("😀".repeat(59) + "…");
  });
});

describe("command length", () => {
  const nfc = "Tiếng Việt, đổi câu ".repeat(10).slice(0, 100);
  const nfd = nfc.normalize("NFD");

  // Red when: the same sentence typed on macOS (NFD) counts longer than in NFC.
  it("counts NFC and NFD the same, and sends NFC", () => {
    expect(nfd.length).toBeGreaterThan(nfc.length);
    expect(commandLength(nfd)).toBe(commandLength(nfc));
    expect(normalizeCommand(nfd)).toBe(nfc.trim());
  });

  it("blocks only above the limit", () => {
    expect(tooLong("a".repeat(COMMAND_MAX))).toBe(false);
    expect(tooLong("a".repeat(COMMAND_MAX + 1))).toBe(true);
    expect(tooLong("ế".normalize("NFD").repeat(COMMAND_MAX))).toBe(false);
  });
});

describe("linkFor", () => {
  it("builds a route from a known kind and a uuid", () => {
    expect(linkFor({ kind: "card", id: ID })).toBe(`/cards/${ID}`);
  });

  // US-18 AC5. Red when: a link can leave the app or the route (core is not trusted to send an href).
  it.each([
    { kind: "javascript:alert(1)", id: ID },
    { kind: "//evil.example", id: ID },
    { kind: "card", id: "../../x" },
    { kind: "card", id: `${ID}?next=//evil.example` },
    { kind: "card", id: "a/b" },
    { kind: "card", id: "" },
  ])("no link for %j", (ref) => {
    expect(linkFor(ref)).toBeNull();
  });
});
