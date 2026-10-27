// @vitest-environment jsdom
// T2.16 (US-05 AC1, AC2, AC9; DESIGN.md §6.5): the result column. A verdict chip, the level of
// understanding in pencil, what was missing, verdicts by unit, the reference answer and the
// sources the grade used. Nothing asks the user to rate themselves.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { GradeResult } from "@/components/review/grade-result";
import type { Result } from "@/lib/review-client";

afterEach(cleanup);

const UNIT_A = "0b8f1d2e-0000-4000-8000-0000000000c1";
const UNIT_B = "0b8f1d2e-0000-4000-8000-0000000000c2";

function result(over: Partial<Result> = {}): Result {
  return {
    overall: "partial",
    understanding: 2,
    missing: ["Server giữ trạng thái SYN-RECEIVED.", "Client gửi lại SYN."],
    units: [{ unit_id: UNIT_A, title: "Thiết lập kết nối TCP", verdict: "partial" }],
    reference_answer: "Client hết timeout thì gửi lại SYN.",
    sources: [
      {
        anchor_id: "0b8f1d2e-0000-4000-8000-0000000000d1",
        quote_text: "Nếu SYN-ACK bị mất, server gửi lại sau timeout.",
        kind: "document",
        page_no: 47,
      },
    ],
    practice: false,
    ...over,
  };
}

describe("GradeResult (T2.16)", () => {
  // US-05 AC2. Red when: a verdict shows the wrong words, or a status colour stands alone.
  it.each([
    ["correct", "Đúng"],
    ["partial", "Đúng một phần"],
    ["incorrect", "Sai"],
    ["forgot", "Không nhớ"],
  ] as const)("US-05 AC2: %s reads %s, with its own mark", (overall, label) => {
    const { container } = render(<GradeResult result={result({ overall })} />);
    const chip = container.querySelector("[data-verdict]");
    expect(chip?.getAttribute("data-verdict")).toBe(overall);
    expect(chip?.textContent).toBe(label);
    expect(chip?.querySelector("svg")).toBeTruthy();
    expect(container.querySelectorAll("[data-verdict]")).toHaveLength(1);
  });

  // DESIGN.md §6.5. Red when: the level shows for a wrong or forgotten answer.
  it.each([
    [1, "chỉ nhớ lại"],
    [2, "hiểu được vì sao"],
    [3, "vận dụng được"],
  ])("US-05 AC2: understanding %i reads %s", (understanding, text) => {
    render(<GradeResult result={result({ overall: "correct", understanding })} />);
    expect(screen.getByText(text)).toBeTruthy();
  });

  it.each(["incorrect", "forgot"] as const)("no understanding for %s", (overall) => {
    render(<GradeResult result={result({ overall, understanding: 2 })} />);
    expect(screen.queryByText("hiểu được vì sao")).toBeNull();
  });

  it("US-05 AC2: what was missing, one line each", () => {
    render(<GradeResult result={result()} />);
    const missing = screen.getByRole("list", { name: "còn thiếu" });
    expect(within(missing).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "Server giữ trạng thái SYN-RECEIVED.",
      "Client gửi lại SYN.",
    ]);
  });

  it("nothing missing: the section is gone", () => {
    render(<GradeResult result={result({ overall: "correct", missing: [] })} />);
    expect(screen.queryByText("còn thiếu")).toBeNull();
  });

  // US-05 AC9. Red when: a question over several units shows one verdict for all of them.
  it("US-05 AC9: a question over several units shows a verdict for each", () => {
    render(
      <GradeResult
        result={result({
          units: [
            { unit_id: UNIT_A, title: "Thiết lập kết nối TCP", verdict: "correct" },
            { unit_id: UNIT_B, title: "Cơ chế timeout", verdict: "incorrect" },
          ],
        })}
      />,
    );
    const units = screen.getByRole("list", { name: "theo từng ý" });
    const items = within(units).getAllByRole("listitem");
    expect(items[0].textContent).toContain("Thiết lập kết nối TCP");
    expect(items[0].textContent).toContain("Đúng");
    expect(items[1].textContent).toContain("Cơ chế timeout");
    expect(items[1].textContent).toContain("Thiếu");
  });

  it("one unit: no per-unit section", () => {
    render(<GradeResult result={result()} />);
    expect(screen.queryByText("theo từng ý")).toBeNull();
  });

  // US-04 AC2, US-05 AC2. Red when: the reference answer or the sources used are missing.
  it("US-05 AC2: the reference answer and the sources the grade used", () => {
    render(
      <GradeResult
        result={result({
          sources: [
            ...result().sources,
            { anchor_id: "0b8f1d2e-0000-4000-8000-0000000000d2", quote_text: "SYN gửi lại sau 1 s.", kind: "notes", page_no: null },
          ],
        })}
      />,
    );
    expect(screen.getByText("Client hết timeout thì gửi lại SYN.")).toBeTruthy();
    expect(screen.getByText("Nếu SYN-ACK bị mất, server gửi lại sau timeout.").closest("mark, blockquote")).toBeTruthy();
    expect(screen.getByText("Giáo trình · tr. 47")).toBeTruthy();
    expect(screen.getByText("SYN gửi lại sau 1 s.")).toBeTruthy();
    expect(screen.getByText("Vở ghi")).toBeTruthy();
  });

  it("a source without a page number names only the document", () => {
    render(
      <GradeResult result={result({ sources: [{ ...result().sources[0], page_no: null }] })} />,
    );
    expect(screen.getByText("Giáo trình")).toBeTruthy();
  });

  // plan: the fake grader's results say so, so a practice run is never taken for a real grade.
  it("a grade from the fake grader is labelled Chấm thử", () => {
    render(<GradeResult result={result({ practice: true })} />);
    expect(screen.getByText("Chấm thử")).toBeTruthy();
  });

  it("a real grade has no such label", () => {
    render(<GradeResult result={result()} />);
    expect(screen.queryByText("Chấm thử")).toBeNull();
  });

  // US-05 AC1. Red when: the result asks the user to rate how well they remembered.
  it("US-05 AC1: nothing asks the user to rate themselves", () => {
    render(<GradeResult result={result()} />);
    expect(screen.queryAllByRole("button")).toEqual([]);
    expect(screen.queryAllByRole("radio")).toEqual([]);
    expect(screen.queryAllByRole("slider")).toEqual([]);
  });
});
