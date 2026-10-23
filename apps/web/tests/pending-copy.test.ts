// Risk register R09: every placeholder sentence (data-copy="tam") is listed here, so a new one
// cannot slip in unnoticed. Adding one means adding it below and to the PR description; the user
// approving one means removing the attribute and its line. T0.13's deploy refuses any left.
// Convention: data-copy="tam" goes on the leaf element that holds exactly the sentence (the regex
// below reads the text right after the tag; a wrapper around <b> or {…} would read wrong).
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(import.meta.dirname, "..");

// Empty since T1.22: the user approved the eleven sentences of T1.18/T1.20 on 23/10 (R09).
const PENDING_COPY: [file: string, text: string][] = [];

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

});
