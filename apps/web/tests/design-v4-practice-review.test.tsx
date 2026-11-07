// @vitest-environment jsdom
// C3-PRACTICE-REVIEW-V4: Luyện tập and Ôn tập in the v4 look. Red when: the practice summary loses its plum
// field or its one primary, the lists stop being white sheets, the empty state loses its mascot, the review
// question and result stop being two sheets, the session summary loses the plum "câu đã làm" field, or a
// colour is hard-coded in these folders.
import { cleanup, render, screen } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PracticeLive } from "@/components/practice/practice-live";
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
