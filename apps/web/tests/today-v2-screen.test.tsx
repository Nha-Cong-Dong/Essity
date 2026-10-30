// T7.13a (US-03, US-15 AC1/AC5/AC6/AC7, DESIGN §6.2/§6.5): Hôm nay v2 and the subject suggestion
// block, one state at a time: exactly one primary button, no banned word, names in buttons.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SubjectSuggestion } from "@/components/subjects/subject-suggestion";
import { TodayV2Screen } from "@/components/today-v2/today-v2-screen";
import { SUBJECT_STATES, TODAY_STATES } from "@/lib/fixtures/today-v2";
import { hasBannedWord, type TodayV2 } from "@/lib/today-v2";

const primaries = (markup: string) => (markup.match(/data-variant="(primary|primary-inverse)"/g) ?? []).length;
const text = (markup: string) => markup.replace(/<[^>]*>/g, " ").replace(/&[a-z#0-9]+;/g, " ");
const draw = (today: TodayV2) => renderToStaticMarkup(<TodayV2Screen today={today} />);

describe("Hôm nay v2 states", () => {
  // Red when: two primaries appear at once (design-critic #2, #4) or none where one is owed.
  const expected: Record<string, number> = {
    busy: 1,
    review: 1,
    learn: 1,
    finished: 0,
    "none-exams": 0,
    "none-textbook": 0,
    "no-subjects": 1,
  };
  for (const [name, count] of Object.entries(expected)) {
    it(`US-03 AC1, US-15 AC1: ${name}: ${count} primary button`, () => {
      expect(primaries(draw(TODAY_STATES[name]))).toBe(count);
    });
  }

  // US-15 AC5. Red when: any drawn sentence uses phải, cần, kịp or trễ.
  it("US-15 AC5: no state uses a banned word", () => {
    for (const [name, today] of Object.entries(TODAY_STATES)) {
      expect(hasBannedWord(text(draw(today))), name).toBe(false);
    }
  });

  it("US-03 AC1: busy: the review session is only in Việc dở, with its own Tiếp tục", () => {
    const markup = draw(TODAY_STATES.busy);
    expect(markup).toContain("Phiên ôn đang dở · câu 7/14");
    expect(markup.match(/\/review\//g)).toHaveLength(1);
    expect(markup).not.toContain(">Bắt đầu<");
  });

  it("US-15 AC1: repeated buttons name their subject", () => {
    const markup = draw(TODAY_STATES.busy);
    expect(markup).toContain('aria-label="Vào buổi học · Mạng máy tính"');
    expect(markup).toContain('aria-label="Mở luyện tập · Mạng máy tính"');
  });

  it("US-15 AC7: a subject without a textbook keeps its own block while another is suggested", () => {
    const markup = draw(TODAY_STATES.learn);
    expect(markup).toContain("chưa có giáo trình chính");
    expect(markup).toContain("Tải giáo trình");
    expect(markup).toContain("Hôm nay không có thẻ hay câu đến hạn.");
    expect(markup).toContain("Lần tới đến hạn: thứ Hai, 02/11");
  });

  it("US-15 AC11: empty reasons keep a way on", () => {
    for (const reason of ["Các môn đã thi xong.", "Chưa có giáo trình để gợi ý."]) {
      const markup = draw(reason.startsWith("Các") ? TODAY_STATES["none-exams"] : TODAY_STATES["none-textbook"]);
      expect(markup).toContain(reason);
      expect(markup).toContain('href="/subjects"');
    }
  });

  it("US-03 AC1: Luyện tập is hidden without a question bank", () => {
    expect(draw(TODAY_STATES["none-exams"])).not.toContain("Luyện tập");
    expect(draw(TODAY_STATES.learn)).toContain("Chưa có câu sẵn sàng.");
  });
});

describe("subject suggestion block", () => {
  const draw1 = (state: string) =>
    renderToStaticMarkup(<SubjectSuggestion subjectId="s1" subjectName="Mạng máy tính" state={SUBJECT_STATES[state]} />);
  const primaryCount: Record<string, number> = {
    suggested: 1,
    "not-suggested": 0,
    finished: 0,
    "exam-over": 0,
    "no-textbook": 1,
    reading: 0,
  };
  for (const [name, count] of Object.entries(primaryCount)) {
    it(`US-15 AC5, AC6: ${name}: ${count} primary, no banned word`, () => {
      const markup = draw1(name);
      expect(primaries(markup)).toBe(count);
      expect(hasBannedWord(text(markup))).toBe(false);
    });
  }

  it("US-15 AC6, US-03 AC7: suggested: nên học, pace line, Ôn riêng môn này secondary, Học tự do quiet", () => {
    const markup = draw1("suggested");
    expect(markup).toContain("Hôm nay nên học: mục 3.2");
    expect(markup).toContain("còn 12 mục (86 trang), 20 ngày");
    expect(markup).toMatch(/data-variant="secondary"[^>]*>Ôn riêng môn này/);
    expect(markup).toMatch(/data-variant="quiet"[^>]*>Học tự do/);
  });

  it("US-15 AC6: not suggested: only the secondary Gợi ý cho hôm nay, no excuse text", () => {
    const markup = draw1("not-suggested");
    expect(markup).toMatch(/data-variant="secondary"[^>]*>Gợi ý cho hôm nay/);
    expect(markup).not.toContain("không phải ngày");
  });

  it("US-15 AC7: no textbook: Học tự do is the primary and not repeated in the footer", () => {
    const markup = draw1("no-textbook");
    expect(markup.match(/Học tự do/g)).toHaveLength(1);
    expect(markup).toContain("Tải giáo trình");
  });

  it("US-15 AC3, AC7: exam over: no suggestion, links to Ôn riêng and Luyện tập", () => {
    const markup = draw1("exam-over");
    expect(markup).not.toContain("Hôm nay nên học");
    expect(markup).toContain("Ôn riêng môn này");
    expect(markup).toContain("Luyện tập");
  });
});
