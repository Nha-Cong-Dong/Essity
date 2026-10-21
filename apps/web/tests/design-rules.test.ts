// Design system v3.1 rules checked on the source (docs/plans/design-architecture-final.md §6, §7;
// plan design-tokens-v3 V10). Each guards against a component added or edited later.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const WEB = path.resolve(import.meta.dirname, "..");

function files(dir: string, pattern: RegExp): string[] {
  return readdirSync(path.join(WEB, dir), { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && pattern.test(entry.name))
    .map((entry) => path.relative(WEB, path.join(entry.parentPath, entry.name)));
}

const read = (file: string) => readFileSync(path.join(WEB, file), "utf-8");
const UI = [...files("app", /\.tsx$/), ...files("components", /\.tsx$/)];
const STYLES = [...files("app", /\.module\.css$/), ...files("components", /\.module\.css$/)];
const GLOBALS = read("app/globals.css");

function offenders(sources: string[], pattern: RegExp): string[] {
  return sources.flatMap((file) =>
    read(file)
      .split("\n")
      .flatMap((line, i) => (pattern.test(line) ? [`${file}:${i + 1}: ${line.trim()}`] : [])),
  );
}

/** Whether `source` declares `name` itself (`[--card-spacing:…]`), as a whole name. */
export function declaresItself(source: string, name: string): boolean {
  return new RegExp(`(?<![\\w-])${name}\\s*:`).test(source);
}

describe("design rules", () => {
  it("finds the sources it checks", () => {
    expect(UI).toContain(path.join("components", "shells.tsx"));
    expect(STYLES).toContain(path.join("components", "notebook", "notebook.module.css"));
  });

  it("§6: no colour named right (it collides with text-align) and no orange", () => {
    expect(offenders(UI, /\b(text|bg|border|decoration|fill|stroke)-(right|cam)\b/)).toEqual([]);
  });

  it("V10: no bg-cover, which Tailwind also reads as background-size: cover", () => {
    expect(offenders(UI, /\bbg-cover\b(?!-)/)).toEqual([]);
  });

  it("every custom property a component reads is declared in globals.css", () => {
    // Set by next/font in app/layout.tsx, not in CSS.
    const runtime = new Set(["--font-be-vietnam-pro", "--font-bricolage", "--font-jetbrains-mono"]);
    const declared = new Set([...GLOBALS.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]));
    const used = [...UI, ...STYLES, "app/globals.css"].flatMap((file) =>
      [...read(file).matchAll(/var\((--[\w-]+)|\((--[\w-]+)\)/g)].map((m) => ({ file, name: m[1] ?? m[2] })),
    );
    const local = (file: string, name: string) => declaresItself(read(file), name);
    const missing = used.filter(
      ({ file, name }) => !declared.has(name) && !runtime.has(name) && !local(file, name),
    );
    expect(missing.map(({ file, name }) => `${file}: ${name}`)).toEqual([]);
  });

  it("a declaration inside a longer name does not count (review of 2ab0d91)", () => {
    expect(declaresItself("x--strong: #000;", "--strong")).toBe(false);
    expect(declaresItself("--strong-line: #000;", "--strong")).toBe(false);
    expect(declaresItself("[--strong:4px]", "--strong")).toBe(true);
  });
});
