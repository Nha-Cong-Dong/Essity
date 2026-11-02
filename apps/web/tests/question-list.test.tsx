// T8.2 (US-14 AC4-AC6): the bank's question list, from the shape the backend sends.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { QuestionList } from "@/components/question-list";
import type { QuestionListOut, QuestionRow } from "@/lib/question-list-types";

const SUBJECT = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const row = (over: Partial<QuestionRow>): QuestionRow => ({
  id: "q1",
  number: 1,
  prompt: "TCP là gì?",
  type_name: "Giải thích",
  origin: "bank",
  answer_source: "bank",
  status: "ready",
  line: "Sẵn sàng",
  waiting_sections: [],
  ...over,
});
const list = (questions: QuestionRow[]): QuestionListOut => ({
  total: questions.length,
  ready: questions.filter((q) => q.status === "ready").length,
  types: [],
  questions,
});
const html = (questions: QuestionRow[]) =>
  renderToStaticMarkup(<QuestionList subjectId={SUBJECT} list={list(questions)} />);

describe("QuestionList", () => {
  it("shows the count, the groups by type and each question's line (AC6)", () => {
    const out = html([
      row({}),
      row({
        id: "q2",
        number: 2,
        type_name: "So sánh",
        status: "waiting",
        line: "Chờ học: mục 2, 3.10",
        waiting_sections: [{ id: "s", number: "2", title: "UDP" }],
      }),
    ]);
    expect(out).toContain("2 câu · 1 sẵn sàng");
    expect(out).toContain("Giải thích");
    expect(out).toContain("So sánh");
    expect(out).toContain("Sẵn sàng");
    expect(out).toContain("Chờ học: mục 2, 3.10");
    expect(out).toContain(`href="/subjects/${SUBJECT}/syllabus"`);
  });

  it("puts unlinked questions apart with one line to fix them (AC3)", () => {
    const out = html([row({}), row({ id: "q3", number: 3, status: "unlinked", line: "Chưa gắn mục. Sửa bằng thanh lệnh." })]);
    expect(out).toContain("Chưa gắn mục. Sửa bằng thanh lệnh.");
    expect(out.indexOf("Chưa gắn mục")).toBeGreaterThan(out.indexOf("TCP là gì?"));
  });

  it("labels an answer the AI wrote and a question with no type", () => {
    const out = html([row({ answer_source: "ai", type_name: "" })]);
    expect(out).toContain("đáp án do AI soạn");
    expect(out).toContain("Chưa có dạng");
  });

  it("says so when there is no bank (AC5)", () => {
    expect(html([])).toContain("Chưa có bộ câu hỏi.");
  });
});
