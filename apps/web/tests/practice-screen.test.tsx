// @vitest-environment jsdom
// T8.7a (US-16 AC1-AC5, AC8; US-17 AC1, AC5, AC6, AC8; US-14): the Luyện tập screen from fixtures.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PracticeScreen } from "@/components/practice/practice-screen";
import { PRACTICE_STATE_IDS, type PracticeState } from "@/lib/fixtures/practice";

afterEach(cleanup);

const PRIMARY = "[data-variant='primary']";
// DESIGN §4. Only the words the app itself writes are scanned: a type name or a question is the
// user's own text (a type may be called "tính toán độ trễ").
// JS \b is ASCII-only ("ễ" is not a word character), so the edges are Unicode lookarounds.
const FORBIDDEN = /(?<!\p{L})(streak|chuỗi|xếp hạng|ranking|trễ|kém|lười|bỏ lỡ|thất bại)(?!\p{L})/iu;

function appCopy(container: HTMLElement): string {
  const clone = container.cloneNode(true) as HTMLElement;
  clone.querySelectorAll("[data-user]").forEach((el) => el.remove());
  return clone.textContent ?? "";
}

const group = (container: HTMLElement, id: string) => container.querySelector(`[data-question=${id}]`) as HTMLElement;

describe("banned words", () => {
  // Red when: the pattern stops matching Vietnamese words (it once did: \b never matched "trễ").
  it.each(["đã trễ", "Chuỗi ngày", "xếp hạng", "bạn kém", "thất bại"])("%s is caught", (text) => {
    expect(text).toMatch(FORBIDDEN);
  });
  it("does not fire inside a longer word", () => {
    expect("trễnải").not.toMatch(FORBIDDEN);
  });
});

describe("every state", () => {
  // US-16 (DESIGN §6.12). Red when: a state has two primaries, or a busy state has none.
  const NONE: PracticeState[] = ["loading", "importing"];
  it.each(PRACTICE_STATE_IDS)("%s: one primary, none inside a closed region, no banned word, no clock", (state) => {
    const { container } = render(<PracticeScreen state={state} />);
    expect(container.querySelectorAll(PRIMARY).length).toBe(NONE.includes(state) ? 0 : 1);
    expect(container.querySelector("details:not([open]) " + PRIMARY)).toBeNull();
    expect(appCopy(container)).not.toMatch(FORBIDDEN);
    expect(container.querySelector("time")).toBeNull();
    expect(container.querySelectorAll("[role=status]").length).toBeLessThanOrEqual(1);
  });
});

describe("home", () => {
  // US-16 AC1. Red when: the summary does not match the rows, or waiting rows beat ready ones.
  it("AC1: the summary line counts the rows; ready rows come before waiting ones", () => {
    const { container } = render(<PracticeScreen state="home" />);
    expect(screen.getByText("6 câu sẵn sàng · 3 đã luyện · 1 đã thuộc")).toBeTruthy();
    const section = container.querySelector("section[aria-labelledby=g-g1]") as HTMLElement;
    const order = [...section.querySelectorAll("[data-question]")].map((li) => li.getAttribute("data-question"));
    expect(order.at(-1)).toBe("q9");
    expect(within(section).getByText("Chờ học: mục 3.4")).toBeTruthy();
  });

  // US-16 AC2. Red when: mastery or timing is missing, or a type with under 3 attempts shows a ratio.
  it("AC2: mastery and neutral timing per type; under 3 attempts says there is not enough data", () => {
    render(<PracticeScreen state="home" />);
    expect(screen.getByText("đúng 7 trên 10 lần gần nhất")).toBeTruthy();
    expect(screen.getByText("đúng 6,5 trên 8 lần gần nhất")).toBeTruthy();
    expect(screen.getAllByText("chưa đủ dữ liệu").length).toBe(1);
    expect(screen.getByText("thường nhanh hơn mốc tham khảo · khoảng 3 phút mỗi câu")).toBeTruthy();
  });

  // US-16 AC4, AC8. Red when: the unlinked row has no hint, or an AI answer has no label.
  it("AC4: an unlinked question names the command bar fix once; an AI answer is labelled", () => {
    render(<PracticeScreen state="home" />);
    expect(screen.getAllByText(/Sửa bằng thanh lệnh/).length).toBe(1);
    expect(screen.getByText(/Chưa gắn mục · Câu 7/)).toBeTruthy();
    expect(screen.getAllByText("đáp án do AI soạn").length).toBe(1);
  });

  // US-16 AC3. Red when: the primary is not the first ready row, or its name drops the visible label.
  it("AC3: the first ready row holds the primary and keeps its visible label", () => {
    const { container } = render(<PracticeScreen state="home" />);
    const primary = container.querySelector(PRIMARY) as HTMLElement;
    expect(primary.textContent).toBe("Làm câu này");
    expect(primary.closest("[data-question]")?.getAttribute("data-question")).toBe("q11");
    expect(document.getElementById(primary.getAttribute("aria-describedby") ?? "")).toBeTruthy();
  });
});

describe("remove and undo", () => {
  // US-16 AC3. Red when: removing needs a dialog, focus is lost, or undo does not bring the row back.
  it("AC3: one tap removes in place, focus on Hoàn tác, undo returns focus to Làm câu này", () => {
    const { container } = render(<PracticeScreen state="home" />);
    fireEvent.click(within(group(container, "q12")).getByText("Gỡ khỏi luyện tập"));
    expect(screen.queryByRole("dialog")).toBeNull();
    const undo = screen.getByRole("button", { name: "Hoàn tác" });
    expect(document.activeElement).toBe(undo);
    expect(screen.getByRole("status").textContent).toBe("Đã gỡ khỏi luyện tập.");
    expect(container.querySelectorAll(PRIMARY).length).toBe(1);
    fireEvent.click(undo);
    expect(group(container, "q12")).toBeTruthy();
    expect((document.activeElement as HTMLElement).textContent).toBe("Làm câu này");
  });

  // Red when: undo on a waiting row drops focus to the page.
  it("AC3: undo on a waiting row puts focus on its Gỡ khỏi luyện tập", () => {
    const { container } = render(<PracticeScreen state="home" />);
    fireEvent.click(within(group(container, "q9")).getByText("Gỡ khỏi luyện tập"));
    fireEvent.click(screen.getByRole("button", { name: "Hoàn tác" }));
    expect(document.activeElement).toBe(within(group(container, "q9")).getByText("Gỡ khỏi luyện tập"));
  });

  it("AC3: removing another row closes the earlier 'Đã gỡ' line", () => {
    const { container } = render(<PracticeScreen state="removed" />);
    expect(container.querySelector("[data-removed=q12]")).toBeTruthy();
    fireEvent.click(within(group(container, "q11")).getByText("Gỡ khỏi luyện tập"));
    expect(container.querySelector("[data-removed=q12]")).toBeNull();
    expect(container.querySelector("[data-removed=q11]")).toBeTruthy();
  });
});

describe("generated candidates", () => {
  // US-17 AC5. Red when: a candidate cannot be kept or discarded, "keep all" exists, or two primaries show.
  it("AC5: each candidate keeps or discards; only the first undecided is primary; no keep-all", () => {
    const { container } = render(<PracticeScreen state="candidates" />);
    const review = container.querySelector("[data-candidates]") as HTMLElement;
    expect(screen.queryByText(/giữ hết/i)).toBeNull();
    expect(screen.getByText("Chỉ dùng thẻ bạn đã học.")).toBeTruthy();
    expect(review.querySelector(PRIMARY)?.closest("li")?.textContent).toContain("Vì sao TCP");
    fireEvent.click(within(review).getAllByText("Đưa vào luyện tập")[0]);
    expect(within(review).getByText("Đã đưa vào luyện tập.")).toBeTruthy();
    expect(container.querySelectorAll(PRIMARY).length).toBe(1);
    expect(review.querySelector(PRIMARY)?.closest("li")?.textContent).toContain("Nêu hai trường hợp");
    fireEvent.click(within(review.querySelector("li:nth-child(2)") as HTMLElement).getByText("Không giữ"));
    expect(within(review).getByText("Sẽ không nhắc lại câu này.")).toBeTruthy();
  });

  // US-17 AC6. Red when: an empty filter offers a retry.
  it("AC6: no candidate passed the filter: a calm line, no retry button", () => {
    render(<PracticeScreen state="no-candidates" />);
    expect(screen.getByText("Chưa có câu sinh thêm nào đủ tốt. Thử lại sau khi học thêm thẻ.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /thử lại/i })).toBeNull();
  });

  // US-17 AC8. Red when: running out of AI turns hides the questions that already exist.
  it("AC8: out of AI turns: generating is disabled with a reason, existing questions stay doable", () => {
    const { container } = render(<PracticeScreen state="quota" />);
    const add = screen.getAllByText("Thêm câu như thế này")[0];
    expect(add.getAttribute("aria-disabled")).toBe("true");
    expect(add.getAttribute("aria-describedby")).toContain("quota-note");
    expect(container.querySelector(PRIMARY)?.textContent).toBe("Làm câu này");
  });
});

describe("no bank", () => {
  // US-17 AC1, US-14. Red when: upload is not the primary, or an unstudied section gets a generate button.
  it("AC1: upload primary; generate only for studied sections; one generation at a time", async () => {
    const { container } = render(<PracticeScreen state="no-bank" />);
    expect(container.querySelector(PRIMARY)?.textContent).toBe("Tải bộ câu hỏi");
    const buttons = screen.getAllByText("Sinh câu luyện tập cho mục này");
    expect(buttons.length).toBe(2);
    expect(screen.getByText("2 mục chưa học xong: học xong mới sinh câu.")).toBeTruthy();
    fireEvent.click(buttons[0]);
    expect(buttons[1].closest("button")?.getAttribute("aria-disabled")).toBe("true");
    await waitFor(() => expect(container.querySelector("[data-candidates]")).toBeTruthy());
    expect(container.querySelectorAll(PRIMARY).length).toBe(1);
  });

  it("AC1: with no studied section it says so and offers no generate button", () => {
    render(<PracticeScreen state="no-bank" sections={[{ id: "s3", label: "3.3", studied: false }]} />);
    expect(screen.getByText("Chưa có mục nào học xong. Hoàn thành một buổi học để sinh câu luyện tập.")).toBeTruthy();
    expect(screen.queryByText("Sinh câu luyện tập cho mục này")).toBeNull();
  });
});

describe("other states", () => {
  it("error: an alert with the retry primary, focused", () => {
    render(<PracticeScreen state="error" />);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Không tải được bộ câu hỏi.");
    expect(document.activeElement).toBe(alert);
  });

  it("empty-ready and importing use the §6.12 words", () => {
    const { unmount } = render(<PracticeScreen state="empty-ready" />);
    expect(screen.getByText("Chưa có câu sẵn sàng. Câu sẽ sẵn sàng khi bạn học xong mục của nó.")).toBeTruthy();
    unmount();
    render(<PracticeScreen state="importing" />);
    expect(screen.getByRole("status").textContent).toMatch(/Đang tách câu từ .+…/);
  });

  it("imported: the suggested type carries a pencil 'gợi ý'", () => {
    render(<PracticeScreen state="imported" />);
    expect(screen.getByText("Đã tách 24 câu. App gợi ý 4 dạng câu; bạn sửa được bằng thanh lệnh.")).toBeTruthy();
    expect(screen.getByText("gợi ý")).toBeTruthy();
  });
});

describe("result", () => {
  // US-16 AC5. Red when: a rubric idea, the AI label, the card line or a usable time is missing.
  it("AC5: rubric per idea, AI label, 'khác thẻ' line, a neutral time line, one primary", () => {
    const { container } = render(<PracticeScreen state="result" />);
    expect(screen.getByText("Độ tin cậy của TCP")).toBeTruthy();
    expect(screen.getByText("đáp án do AI soạn")).toBeTruthy();
    expect(screen.getByText(/Đáp án này khác với thẻ/)).toBeTruthy();
    expect(screen.getByText(/Bạn trả lời trong 2 phút 10 giây. Dạng này thường mất khoảng 3 phút./)).toBeTruthy();
    expect(container.querySelectorAll(PRIMARY).length).toBe(1);
  });
  it("AC5: no time line when the time is not usable", () => {
    render(<PracticeScreen state="result" showTiming={false} />);
    expect(screen.queryByText(/Bạn trả lời trong/)).toBeNull();
  });
});
