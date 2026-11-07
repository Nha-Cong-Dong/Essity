// PREDEPLOY-FIX-A E-08: Today's number is "ready and never attempted", so its label says "mới chưa làm",
// not "sẵn sàng" (the practice page's "sẵn sàng" counts every ready question).
import { describe, expect, it } from "vitest";

import { practiceLine } from "@/lib/today-v2";

describe("E-08", () => {
  it("E-08 Today's practice line names what it counts", () => {
    expect(practiceLine({ subject_id: "s", name: "Mạng", ready: 2, kinds: 1 })).toBe("Mạng: 2 câu mới chưa làm · 1 dạng");
  });
});
