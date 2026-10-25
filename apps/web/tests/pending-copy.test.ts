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
// again (the user approved T2.3b's six delete strings on 25/10).
const PENDING_COPY: [file: string, text: string][] = [];

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
