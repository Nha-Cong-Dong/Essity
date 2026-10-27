// Risk register R09: every placeholder sentence (data-copy="tam") is listed here, so a new one
// cannot slip in unnoticed. Adding one means adding it below and to the PR description; the user
// approving one means removing the attribute and its line. T0.13's deploy refuses any left.
// Convention: data-copy="tam" goes on the leaf element that holds exactly the sentence (the regex
// below reads the text right after the tag; a wrapper around <b> or {…} would read wrong).
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(import.meta.dirname, "..");

// T1.22 emptied it (the user approved T1.18/T1.20's sentences on 23/10 and 24/10); T2.3c emptied it
// again (the user approved T2.3b's six delete strings on 25/10). T2.14 adds /today's: the backlog
// note and "Ôn thêm" (US-03 AC5), the two states with nothing to ask, and a start that failed.
// T2.15/T2.13 add the answer screen's (plan t2.15-t2.13-t2.16-answer-grade.md "Câu tạm").
const PENDING_COPY: [file: string, text: string][] = [
  ["components/today/today-screen.tsx", "Các môn của bạn đều đã thi xong."],
  ["components/today/today-screen.tsx", "Môn của bạn chưa có câu hỏi nào để ôn."],
  [
    "components/today/today-screen.tsx",
    'Để kịp thi {today.backlog.subject_name} cần thêm khoảng{" "} {extraSessions(today.backlog.sessions, today.backlog.days)} phiên trong{" "} {today.backlog.days} ngày.',
  ],
  ["components/today/today-screen.tsx", "Ôn thêm"],
  ["components/today/start-button.tsx", "Chưa mở được phiên. Thử lại sau giây lát."],
  ["components/review/answer-box.tsx", "Câu trả lời dài hơn 4.000 ký tự. Rút gọn bớt rồi gửi."],
  ["components/review/review-screen.tsx", "kết quả hiện ở đây sau khi gửi"],
  ["components/review/review-screen.tsx", "Câu trả lời của bạn · đã lưu {clock(at)}"],
  ["components/review/review-screen.tsx", "Chưa gửi được. Câu trả lời vẫn ở đây, bạn gửi lại nhé."],
  ["components/review/review-screen.tsx", "Chưa chấm được. Câu trả lời của bạn đã được lưu."],
  ["components/review/review-screen.tsx", "Chấm bài đang tạm tắt. Câu trả lời của bạn đã được lưu."],
  ["components/review/review-screen.tsx", "Phiên ôn này đã kết thúc."],
  ["components/review/review-screen.tsx", "Còn {ids.length} câu chưa chấm"],
  ["components/review/review-screen.tsx", "Chưa chấm được"],
  ["components/review/review-screen.tsx", "Đã chấm"],
  ["components/review/grade-result.tsx", "Chấm thử"],
  ["components/review/source-quote.tsx", "Vở ghi"],
  ["components/review/source-quote.tsx", "Giáo trình"],
  ["components/review/source-quote.tsx", "Giáo trình · tr. {source.page_no}"],
  // plan D-8: the way out until T2.17's summary (last question, session over, answers ungraded)
  ["components/review/review-screen.tsx", "Về trang chính"],
  ["components/review/review-screen.tsx", "Về trang chính"],
  ["components/review/review-screen.tsx", "Về trang chính"],
  // T2.17 summary (screens-html/screens/session-done.html)
  ["components/review/summary.tsx", "Đã lưu phần bạn làm"],
  ["components/review/summary.tsx", "Xong phiên hôm nay"],
  ["components/review/summary.tsx", "{total - answered} câu còn lại sẽ quay về lần ôn sau."],
  ["components/review/summary.tsx", "câu đã làm"],
  ["components/review/summary.tsx", "câu đúng"],
  ["components/review/summary.tsx", "Phiên tiếp theo:"],
  ["components/review/summary.tsx", "Về trang chính"],
  ["components/review/summary.tsx", "Ôn thêm"],
];

function sources(dir: string): string[] {
  return readdirSync(path.join(ROOT, dir), { recursive: true, encoding: "utf-8" })
    .filter((file) => file.endsWith(".tsx"))
    .map((file) => path.join(dir, file).replaceAll("\\", "/"));
}

function taggedIn(text: string): string[] {
  return [...text.matchAll(/data-copy="tam"[^>]*>\s*([^<]+?)\s*</g)].map((match) =>
    match[1].replace(/\s+/g, " "),
  );
}

function tagged(): [string, string][] {
  return ["app", "components"].flatMap(sources).flatMap((file) =>
    taggedIn(readFileSync(path.join(ROOT, file), "utf-8")).map((text): [string, string] => [file, text]),
  );
}

describe("placeholder sentences (risk register R09)", () => {
  // Red when: a data-copy="tam" sentence is added, changed or approved without updating the list.
  it("every data-copy=\"tam\" in app/ and components/ is listed", () => {
    expect(tagged().sort()).toEqual([...PENDING_COPY].sort());
  });

  // Red when: the scan stops reading the screens (wrong extension, a path joined wrongly on
  // Windows), so the list above matches an empty scan whatever the sources hold.
  it("the scan reads the screens", () => {
    expect(sources("components")).toContain("components/subjects/subject-list.tsx");
    expect(sources("app").length).toBeGreaterThan(0);
  });

  // Red when: the pattern no longer finds a tagged sentence, even one spread over lines.
  it("the pattern finds a tagged sentence", () => {
    expect(taggedIn('<p className="x" data-copy="tam">\n  Câu mới.\n</p>')).toEqual(["Câu mới."]);
    expect(taggedIn('<p data-copy="tam" className="x">Nhãn đứng trước</p>')).toEqual(["Nhãn đứng trước"]);
    expect(taggedIn('<p data-copy="tam">Hai   dòng\n  một câu</p><p>Không nhãn</p>')).toEqual([
      "Hai dòng một câu",
    ]);
    expect(taggedIn('<p data-copy="final">Đã duyệt</p>')).toEqual([]);
  });
});
