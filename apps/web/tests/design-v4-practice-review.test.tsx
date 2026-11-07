// @vitest-environment jsdom
// C3-PRACTICE-REVIEW-V4: Luyện tập and Ôn tập in the v4 look. Red when: the practice summary loses its plum
// field or its one primary, the lists stop being white sheets, the empty state loses its mascot, the review
// question and result stop being two sheets, the session summary loses the plum "câu đã làm" field, or a
// colour is hard-coded in these folders.
import { act, cleanup, render, screen } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GradeResult } from "@/components/review/grade-result";
import { SourceQuote } from "@/components/review/source-quote";
import { PracticeAnswer } from "@/components/practice/practice-answer";
import { PracticeLive } from "@/components/practice/practice-live";
import { ReviewScreen } from "@/components/review/review-screen";
import type { PracticeApi, PracticeView } from "@/lib/practice-client";
import type { Current, Result, ReviewApi } from "@/lib/review-client";
import { Summary } from "@/components/review/summary";
import type { QuestionListOut } from "@/lib/question-list-types";

vi.mock("@/lib/navigate", () => ({ go: () => undefined }));
afterEach(cleanup);

const SUBJECT = "0b8f1d2e-0000-4000-8000-000000000001";
const row = (n: number, status: "ready" | "waiting", due = false) => ({
  id: `0b8f1d2e-0000-4000-8000-0000000000a${n}`,
  number: n,
  prompt: `Câu số ${n}`,
  origin: "bank" as const,
  status,
  answer_source: "bank" as const,
  type_name: "So sánh",
  line: status === "ready" ? "Sẵn sàng" : "Chờ học: phần 3.4",
  waiting_sections: [],
  due,
});
const list = (questions: ReturnType<typeof row>[]): QuestionListOut => ({
  total: questions.length,
  ready: questions.filter((q) => q.status === "ready").length,
  due_today: questions.filter((q) => q.due).length,
  types: [],
  questions,
});

describe("Luyện tập (v4)", () => {
  it("has a plum summary field and white sheets for the lists", () => {
    const { container } = render(
      <PracticeLive subjectId={SUBJECT} subjectName="Mạng" list={list([row(1, "ready", true), row(2, "waiting")])} types={[]} />,
    );
    const field = container.querySelector('[data-practice-today][data-tier="field"]');
    expect(field).not.toBeNull();
    expect(field?.querySelectorAll("button")).toHaveLength(1);
    expect(container.querySelector('[data-practised][data-tier="sheet"]')).not.toBeNull();
    expect(container.querySelector("#waiting")?.closest('[data-tier="sheet"]')).not.toBeNull();
    expect(container.querySelector('[data-tier="tint"]')).toBeNull();
  });

  it("the empty bank is a sheet with the waiting mascot and one action", () => {
    const { container } = render(<PracticeLive subjectId={SUBJECT} subjectName="Mạng" list={list([])} types={[]} />);
    const empty = container.querySelector('[data-empty][data-tier="sheet"]');
    expect(empty?.querySelector('[data-mascot="cho"]')).not.toBeNull();
    expect(screen.getAllByText("Tải bộ câu hỏi")).toHaveLength(1);
  });

  it("with nothing unlocked, says so in a sheet with the mascot and one action to study", () => {
    const { container } = render(<PracticeLive subjectId={SUBJECT} subjectName="Mạng" list={list([row(1, "waiting")])} types={[]} />);
    expect(container.querySelector('[data-mascot="cho"]')).not.toBeNull();
    expect(screen.getAllByText("Vào buổi học")).toHaveLength(1);
  });
});

describe("Ôn tập summary (v4)", () => {
  it("shows the done count on a plum field with the cheering mascot and the right count on a sheet", () => {
    const { container } = render(
      <Summary answered={4} total={5} correct={3} nextDay={null} busy={false} onLeave={() => undefined} onMore={() => undefined} />,
    );
    const field = container.querySelector('[data-tier="field"]');
    expect(field?.querySelector('[data-testid="answered"]')?.textContent).toBe("4");
    expect(field?.querySelector('[data-mascot="khen"]')).not.toBeNull();
    expect(container.querySelector('[data-tier="sheet"] [data-testid="correct"]')?.textContent).toBe("3");
  });
});

const RESULT: Result = {
  grade_id: "0b8f1d2e-0000-4000-8000-0000000000e1",
  overall: "partial",
  understanding: 2,
  missing: ["Thiếu ý A."],
  units: [{ unit_id: "u1", title: "Ý chính", verdict: "partial" }],
  reference_answer: "Đáp án mẫu.",
  sources: [{ anchor_id: "0b8f1d2e-0000-4000-8000-0000000000d1", quote_text: "Trích dẫn.", kind: "document", page_no: 3 }],
  practice: false,
};

describe("GradeResult and SourceQuote (v4)", () => {
  it("nested blocks are sunken and the source quote is a white row inside them", () => {
    const { container } = render(<GradeResult result={RESULT} />);
    expect(container.querySelector(".bg-sunken")).not.toBeNull();
    expect(container.querySelector("figure.bg-sheet blockquote")).not.toBeNull();
    expect(container.querySelector('[data-tier="field"]')).toBeNull();
  });

  it("SourceQuote is a white row with the quote and its citation", () => {
    const { container } = render(<SourceQuote source={RESULT.sources[0]!} />);
    const fig = container.querySelector("figure");
    expect(fig?.className).toContain("bg-sheet");
    expect(fig?.querySelector("blockquote")?.textContent).toBe("Trích dẫn.");
    expect(fig?.querySelector("figcaption")?.textContent).toBe("Giáo trình · tr. 3");
  });
});

describe("PracticeAnswer (v4)", () => {
  const draft: PracticeView = {
    attempt_id: "0b8f1d2e-0000-4000-8000-0000000000b1",
    status: "draft",
    answer_text: "",
    dont_remember: false,
    failure: null,
    grading: null,
    question: { id: "q1", prompt: "So sánh TCP và UDP." },
    result: null,
    submitted_at: null,
    timing_ok: null,
  };
  const api = (view: PracticeView) =>
    ({
      open: vi.fn(async () => ({ ok: true, data: view })),
      saveDraft: vi.fn(async () => ({ ok: true, data: null })),
      read: vi.fn(async () => ({ ok: true, data: view })),
    }) as unknown as PracticeApi;

  it("while writing: one sheet for the question, no result sheet", async () => {
    let c!: HTMLElement;
    await act(async () => {
      c = render(<PracticeAnswer questionId="q1" api={api(draft)} onNext={() => undefined} />).container;
    });
    expect(c.querySelectorAll('[data-tier="sheet"]')).toHaveLength(1);
    expect(c.querySelector("section[aria-live]")).toBeNull();
  });

  it("after sending: the question sheet and a separate live result sheet", async () => {
    const graded: PracticeView = {
      ...draft,
      status: "submitted",
      grading: "graded",
      answer_text: "TCP tin cậy.",
      submitted_at: "2026-11-02T08:00:00Z",
      result: {
        grade_id: RESULT.grade_id,
        overall: "partial",
        missing: ["Thiếu ý A."],
        units: [{ text: "Ý", met: false }],
        reference_answer: "Mẫu.",
        answer_origin: "ai",
        differs_from_card_id: null,
      },
    };
    let c!: HTMLElement;
    await act(async () => {
      c = render(<PracticeAnswer questionId="q1" api={api(graded)} onNext={() => undefined} />).container;
    });
    const sheets = c.querySelectorAll('[data-tier="sheet"]');
    expect(sheets).toHaveLength(2);
    expect(sheets[0]?.querySelector("h1")).not.toBeNull();
    expect(sheets[1]?.getAttribute("aria-live")).toBe("polite");
    expect(sheets[1]?.querySelector("[data-verdict]")).not.toBeNull();
  });
});

describe("ReviewScreen (v4)", () => {
  const SESSION = "5a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d";
  const cur: Current = {
    done: false,
    ungraded: [],
    position: 1,
    total: 3,
    question: {
      id: "8d3e4f5a-6b7c-4d8e-9f0a-1b2c3d4e5f6a",
      kind: "card",
      prompt: "Vì sao có ngày và đêm?",
      subject: { id: "9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b", name: "Địa lý" },
      unit_ids: [],
      reason: { kind: "review", retrievability: 0.7, days_since_last: 6 },
    },
    attempt: { id: "a1", status: "draft", answer_text: "", dont_remember: false },
  };
  const mk = (current: unknown) =>
    ({
      current: vi.fn(async () => ({ ok: true, data: current })),
      open: vi.fn(async () => ({ ok: true, data: cur.attempt })),
      saveDraft: vi.fn(async () => ({ ok: true, data: null })),
      read: vi.fn(async () => ({ ok: false, error: "x" })),
    }) as unknown as ReviewApi;
  const show = async (api: ReviewApi) => {
    let c!: HTMLElement;
    await act(async () => {
      c = render(<ReviewScreen sessionId={SESSION} api={api} />).container;
    });
    return c;
  };

  it("the question and the result rail are two white sheets", async () => {
    const c = await show(mk(cur));
    expect(c.querySelectorAll('[data-tier="sheet"]')).toHaveLength(2);
    expect(c.querySelector('[data-tier="sheet"] h1')?.textContent).toBe("Vì sao có ngày và đêm?");
  });

  it("Ended is a sheet with the cheering mascot and one action", async () => {
    const api = mk(cur);
    (api.current as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: false, error: "session_ended" });
    const c = await show(api);
    const ended = c.querySelector('[aria-label="Phiên ôn đã kết thúc"]');
    expect(ended?.getAttribute("data-tier")).toBe("sheet");
    expect(ended?.querySelector('[data-mascot="khen"]')).not.toBeNull();
    expect(ended?.querySelectorAll("button")).toHaveLength(1);
  });

  it("Ungraded lists the unfinished answers inside a sheet with one way out", async () => {
    const c = await show(mk({ done: true, ungraded: ["a9"] }));
    expect(screen.getByText("Còn 1 câu chưa chấm").closest('[data-tier="sheet"]')).not.toBeNull();
    expect(c.querySelectorAll("button").length).toBeGreaterThan(0);
  });
});

describe("no hard-coded colour", () => {
  it("none in components/practice and components/review", () => {
    for (const dir of ["practice", "review"]) {
      const base = path.join(process.cwd(), "components", dir);
      for (const file of readdirSync(base)) {
        const src = readFileSync(path.join(base, file), "utf8");
        expect(src, `${dir}/${file}`).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/);
      }
    }
  });
});
