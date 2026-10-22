// Risk register R09: every placeholder sentence (data-copy="tam") is listed here, so a new one
// cannot slip in unnoticed. Adding one means adding it below and to the PR description; the user
// approving one means removing the attribute and its line. T0.13's deploy refuses any left.
// Convention: data-copy="tam" goes on the leaf element that holds exactly the sentence (the regex
// below reads the text right after the tag; a wrapper around <b> or {…} would read wrong).
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { PLACEHOLDER_MESSAGES, SUBJECT_MESSAGES } from "@/lib/subject-copy";

const ROOT = path.resolve(import.meta.dirname, "..");

const PENDING_COPY: [file: string, text: string][] = [
  ["components/subjects/subject-fields.tsx", "{SUBJECT_MESSAGES[code]}"],
  ["components/subjects/subject-list.tsx", "Lưu"],
  ["components/subjects/subject-list.tsx", "Hủy"],
  ["components/subjects/subjects-loader.tsx", "Không tải được danh sách môn."],
  ["components/subjects/upload-step.tsx", "Tải tài liệu sẽ có ở bản sau."],
  ["components/today-note.tsx", "Lịch ôn hôm nay sẽ hiện ở đây sớm."],
];

const PENDING_MESSAGES = [
  "Ngày thi cách quá xa (tối đa 2 năm). Kiểm tra lại năm nhé.",
  "Tên môn dài tối đa 200 ký tự.",
  "Không tìm thấy môn này. Tải lại trang rồi thử lại.",
];

function sources(dir: string): string[] {
  return readdirSync(path.join(ROOT, dir), { recursive: true, encoding: "utf-8" })
    .filter((file) => file.endsWith(".tsx"))
    .map((file) => path.join(dir, file).replaceAll("\\", "/"));
}

function tagged(): [string, string][] {
  return ["app", "components"].flatMap(sources).flatMap((file) => {
    const text = readFileSync(path.join(ROOT, file), "utf-8");
    return [...text.matchAll(/data-copy="tam"[^>]*>\s*([^<]+?)\s*</g)].map(
      (match): [string, string] => [file, match[1].replace(/\s+/g, " ")],
    );
  });
}

describe("placeholder sentences (risk register R09)", () => {
  // Red when: a data-copy="tam" sentence is added, changed or approved without updating the list.
  it("every data-copy=\"tam\" in app/ and components/ is listed", () => {
    expect(tagged().sort()).toEqual([...PENDING_COPY].sort());
  });

  it("every placeholder message is listed", () => {
    expect([...PLACEHOLDER_MESSAGES].map((code) => SUBJECT_MESSAGES[code]).sort()).toEqual([...PENDING_MESSAGES].sort());
  });
});
