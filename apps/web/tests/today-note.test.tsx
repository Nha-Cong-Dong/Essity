// @vitest-environment jsdom
// Plan K16: /today says what is true for the user until T2.14 fills it with the day's session.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

// The project's link-as-button (Button render={<a/>}) is found by its text, as in subject-screens.

import { TodayNote } from "@/components/today-note";

afterEach(cleanup);

describe("TodayNote (plan K16)", () => {
  it("no subject yet: DESIGN.md §6.3's invitation to create the first one", () => {
    render(<TodayNote hasSubjects={false} />);
    expect(screen.getByText("Chưa có môn nào. Tạo môn đầu tiên bằng tên và ngày thi.")).toBeTruthy();
    expect(screen.getByText("Tạo môn").closest("a")?.getAttribute("href")).toBe("/subjects/new");
  });

  // Red when: someone with subjects is told they have none (pm-audit 23/10 #2).
  it("with subjects: never says there are none, and points to the subjects", () => {
    render(<TodayNote hasSubjects />);
    expect(screen.queryByText(/Chưa có môn nào/)).toBeNull();
    const sentence = screen.getByText("Lịch ôn hôm nay sẽ hiện ở đây sớm.");
    expect(sentence.getAttribute("data-copy")).toBe("tam");
    expect(screen.getByText("Môn học").closest("a")?.getAttribute("href")).toBe("/subjects");
  });
});
