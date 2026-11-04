import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SubjectStatsBlock } from "@/components/subjects/subject-stats-block";

const EMPTY = {
  id: "s",
  name: "Xác suất thống kê (giáo trình thật)",
  examOn: null,
  daysLeft: null,
  syllabus: { studied: 1, leaves: 70, pagesDone: 0, pages: 0 },
  bank: null,
  retention: null,
  skippedCards: 0,
};

// V22 §8.2: only numbers are big; no data is "—" with a line that says what to do.
describe("subject stats block", () => {
  it("shows a dash and a hint, never 'chưa có' at display size", () => {
    const html = renderToStaticMarkup(<SubjectStatsBlock stats={EMPTY} />);
    expect(html).toContain("—");
    expect(html).toContain("Học một buổi để có thẻ");
    expect(html).not.toContain("chưa có");
    expect(html.match(/tabular-nums/g)?.length).toBe(1); // only the "1/70" number is large
  });
});
