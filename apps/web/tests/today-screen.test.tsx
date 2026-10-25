// T2.14 (US-03, DESIGN.md §6.3; plan t2.8-t2.9-t2.14-today-session.md): /today draws what
// GET /v1/today answers, one state at a time, with exactly one primary button.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { TodayScreen } from "@/components/today/today-screen";
import type { Today } from "@/lib/today";

const MMT = "3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b";
const HDH = "6b1c2d3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e";
const SUBJECTS = [
  { id: MMT, name: "Mạng máy tính", exam_date: "2026-12-15", days_until_exam: 54 },
  { id: HDH, name: "Hệ điều hành", exam_date: "2026-12-20", days_until_exam: 59 },
];
const BASE: Today = {
  learning_day: "2026-10-21",
  state: "ready",
  session: null,
  in_progress: null,
  backlog: null,
  next_day: null,
  subjects: SUBJECTS,
};

const draw = (today: Partial<Today>) => renderToStaticMarkup(<TodayScreen today={{ ...BASE, ...today }} />);
// The primary button is the only element styled as one: primary or primary-inverse.
const primaries = (markup: string) =>
  (markup.match(/data-variant="(primary|primary-inverse)"/g) ?? []).length;

describe("/today screen (T2.14)", () => {
  // US-03 AC1. Red when: the count, minutes or subjects are missing, or a second primary appears.
  it("ready: count, minutes, subjects and one Bắt đầu", () => {
    const markup = draw({
      session: {
        question_count: 14,
        minutes: 21,
        subjects: [
          { id: MMT, name: "Mạng máy tính" },
          { id: HDH, name: "Hệ điều hành" },
        ],
      },
    });
    expect(markup).toContain("Phiên ôn tối nay");
    expect(markup).toMatch(/>14<\/span>/);
    expect(markup).toContain("khoảng 21 phút · Mạng máy tính, Hệ điều hành");
    expect(markup).toContain("Bắt đầu");
    expect(primaries(markup)).toBe(1);
    expect(markup).toContain("thứ Tư, 21/10");
  });

  // US-08 AC3, DESIGN §6.3. Red when: an open session still shows Bắt đầu.
  it("in progress: Đang ở câu 7/14 and Tiếp tục to the session", () => {
    const markup = draw({
      state: "in_progress",
      in_progress: { session_id: HDH, position: 7, total: 14 },
    });
    expect(markup).toContain("Đang ở: câu 7/14");
    expect(markup).toContain("Tiếp tục");
    expect(markup).toContain(`href="/review/${HDH}"`);
    expect(markup).not.toContain("Bắt đầu");
    expect(primaries(markup)).toBe(1);
  });

  // US-03 AC5. Red when: the backlog sentence is red, warns, or the "Ôn thêm" button is primary.
  it("backlog: a neutral sentence and Ôn thêm as a secondary button", () => {
    const markup = draw({
      session: { question_count: 20, minutes: 30, subjects: [{ id: MMT, name: "Mạng máy tính" }] },
      backlog: { subject_id: MMT, subject_name: "Mạng máy tính", sessions: 16, days: 10 },
    });
    expect(markup).toContain("Để kịp thi Mạng máy tính cần thêm khoảng 6 phiên trong 10 ngày.");
    expect(markup).toContain("Ôn thêm");
    expect(primaries(markup)).toBe(1);
    expect(markup).not.toMatch(/destructive|text-red|warning|cảnh báo/i);
  });

  // US-03 AC6. Red when: nothing to review leaves the screen empty or without the next day.
  it("rested: Hôm nay không cần ôn and the next session's day", () => {
    const markup = draw({ state: "rested", next_day: "2026-10-22" });
    expect(markup).toContain("Hôm nay không cần ôn.");
    expect(markup).toContain("Phiên tiếp theo:");
    expect(markup).toContain("thứ Năm, 22/10");
    expect(primaries(markup)).toBe(0);
  });

  it("no subjects: the empty state with Tạo môn", () => {
    const markup = draw({ state: "no_subjects", subjects: [] });
    expect(markup).toContain("Chưa có môn nào.");
    expect(markup).toContain('href="/subjects/new"');
    expect(primaries(markup)).toBe(1);
  });

  // PLAN T2.14 / DESIGN §6.3: before T4.13 a neutral sentence, no button, no "Sau buổi học".
  it("no questions yet: a neutral sentence and no button", () => {
    const markup = draw({ state: "no_questions" });
    expect(primaries(markup)).toBe(0);
    expect(markup).not.toContain("Ghi buổi học");
    expect(markup).toContain("Môn đang ôn");
  });

  it("every exam is over: a neutral sentence and no button", () => {
    const markup = draw({ state: "all_exams_over" });
    expect(primaries(markup)).toBe(0);
    expect(markup).toContain('data-copy="tam"');
  });

  it("the subjects tile lists each subject with its exam date", () => {
    const markup = draw({ state: "rested", next_day: "2026-10-22" });
    expect(markup).toContain("Môn đang ôn");
    expect(markup).toContain("Mạng máy tính");
    expect(markup).toContain("thi 15/12/2026");
  });
});
