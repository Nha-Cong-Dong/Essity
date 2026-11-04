import { describe, expect, it } from "vitest";

import { appendMention, reconcileMentions } from "@/lib/session-study/mention";

const doc = { id: "d1", name: "Slide chương 3", role: "auxiliary" };

describe("V11 appendMention", () => {
  // Red when: a file that went into the store is not mentioned, so "Ghi lại" with only a file has nothing to send.
  it("mentions the stored file in an empty field, with the range of the chip", () => {
    const out = appendMention("", doc, []);
    expect(out.text).toBe("@Slide chương 3 ");
    expect(out.mentions).toEqual([{ docId: "d1", name: "Slide chương 3", start: 0, end: 15 }]);
  });

  it("goes after the words already written, and a second upload of the same file adds nothing", () => {
    const out = appendMention("Hôm nay học", doc, []);
    expect(out.text).toBe("Hôm nay học @Slide chương 3 ");
    const [m] = out.mentions;
    expect(out.text.slice(m.start, m.end)).toBe("@Slide chương 3");
    expect(appendMention(out.text, doc, out.mentions)).toEqual(out);
    // Editing before it keeps the chip, as for a chosen mention.
    expect(reconcileMentions(out.text, `Ghi chú. ${out.text}`, out.mentions).mentions).toHaveLength(1);
  });
});
