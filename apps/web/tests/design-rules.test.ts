// Design system v3.1 rules checked on the source (docs/plans/design-architecture-final.md §6, §7;
// plan design-tokens-v3 V10). Each guards against a component added or edited later.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { buttonProblems } from "./jsx-rules";

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

  it("§7 #4, #20: type steps and role radii, not pixel sizes, hand radii or Tailwind's xl scale", () => {
    expect(offenders(UI, /text-\[\d+px\]|rounded-\[|rounded-(xs|xl|2xl|3xl|4xl)\b/)).toEqual([]);
  });

  it("a colour from a custom property names its type: text-(--x) is read as a font size", () => {
    // primary-inverse lost its label this way: text-(--inverse-fg) became a font size.
    expect(offenders(UI, /\b(text|bg|border|decoration|outline|ring|fill|stroke|shadow)-\(--/)).toEqual([]);
  });

  it("no Tailwind dark: variant in components: dark mode is tokens only", () => {
    expect(offenders(UI, /\bdark:/)).toEqual([]);
  });

  it("§3.1: italic belongs to the pencil; what the user wrote is upright pink", () => {
    expect(offenders(UI, /font-hand[^"]*text-hong|text-hong[^"]*font-hand/)).toEqual([]);
  });

  it("buttons: height from the size scale, a busy submit is pending (read as JSX, review of 4b86dc4)", () => {
    const problems = UI.flatMap((file) =>
      buttonProblems(read(file), file).map((p) => `${file}:${p.line}: ${p.text}`),
    );
    expect(problems).toEqual([]);
  });

  it("the JSX rule sees a Button over several lines with an element in its props", () => {
    const source = [
      "const x = (",
      "  <Button",
      '    render={<a href="/login" />}',
      "    nativeButton={false}",
      '    className="h-14 w-full"',
      "  />",
      ");",
      'const y = <Button type="submit" disabled={busy || late}>Gửi</Button>;',
    ].join("\n");
    expect(buttonProblems(source)).toEqual([
      { line: 2, text: "height set by class: use size" },
      { line: 8, text: "busy submit only disabled: use pending" },
    ]);
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
