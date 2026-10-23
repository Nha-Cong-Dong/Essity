// Product rule (the user, 23/10; US-11 dropped, PRD:242-244): the app never asks for a GPA or a
// starting point. A product rule kept by scanning the source, as CONVENTIONS allows for rules the
// user set (T1.22 plan E9): only the rule's own words, never the names of the removed code.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const WEB = path.resolve(import.meta.dirname, "..");
const FORBIDDEN = [/gpa/i, /mốc ban đầu/iu, /điểm xuất phát/iu, /prior_ready_days/];

function sourceFiles(dir: string): string[] {
  return readdirSync(path.join(WEB, dir), { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && /\.(ts|tsx)$/.test(entry.name))
    .map((entry) => path.relative(WEB, path.join(entry.parentPath, entry.name)));
}

const SOURCES = [
  ...sourceFiles("app"),
  ...sourceFiles("components"),
  ...sourceFiles("lib"),
  ...readdirSync(WEB).filter((name) => /^(proxy|instrumentation.*)\.ts$/.test(name)),
];

/** The forbidden words in `text`. */
export function gradeWords(text: string): string[] {
  return FORBIDDEN.flatMap((word) => text.match(new RegExp(word.source, `${word.flags}g`)) ?? []);
}

describe("no grade or starting-point questions (US-11 dropped)", () => {
  it("scans the sources", () => {
    expect(SOURCES).toContain("proxy.ts");
    expect(SOURCES).toContain(path.join("components", "auth", "verify-email.tsx"));
  });

  // Red when: a page, a route or its copy asks for a GPA or a starting point again.
  it("no source names a GPA or a starting point", () => {
    const hits = SOURCES.flatMap((file) =>
      gradeWords(readFileSync(path.join(WEB, file), "utf-8")).map((word) => `${file}: ${word}`),
    );
    expect(hits).toEqual([]);
  });

  // Red when: the scan is too narrow (misses a cased or joined name) or too wide (catches CSS).
  it("catches 'GPA hiện tại', gpa_before, priorGpa and the old copy; leaves items-baseline", () => {
    expect(gradeWords('label="GPA hiện tại"')).toEqual(["GPA"]);
    expect(gradeWords("const gpa_before = 1")).toEqual(["gpa"]);
    expect(gradeWords("let priorGpa")).toEqual(["Gpa"]);
    expect(gradeWords("Ghi điểm xuất phát · Mốc ban đầu")).toHaveLength(2);
    expect(gradeWords('className="items-baseline"')).toEqual([]);
  });
});
