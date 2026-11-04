// Design system v3.1 rules checked on the source (docs/design/visual-system.md §6, §7;
// plan design-tokens-v3 V10). Each guards against a component added or edited later.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { TYPE_STEPS } from "@/lib/utils";

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

// A Nx row that sets `next` or `pick` (V22 #9).
const NX_VARIANT = /<Nx(?:Row|Kind)\b[^>]*\b(?:next|pick)\b/g;

describe("design rules", () => {
  it("finds the sources it checks", () => {
    expect(UI).toContain(path.join("components", "shells.tsx"));
    expect(STYLES).toContain(path.join("components", "notebook", "notebook.module.css"));
  });

  it("§6: no colour named right (it collides with text-align)", () => {
    expect(offenders(UI, /\b(text|bg|border|decoration|fill|stroke)-right\b/)).toEqual([]);
  });

  // V22 decisions #9: --cam is the one second colour, for "suggested / next" rows only. It may be
  // named in the NxList components and nowhere else, so it cannot spread to status, charts or buttons.
  it("V22: cam appears only in ui/nx-list.tsx", () => {
    const named = UI.filter((f) => /\b(?:text|bg|border|ring|inset-ring|fill|stroke)-cam\b|\(--cam\)/.test(read(f)));
    expect(named.map((f) => f.replaceAll("\\", "/"))).toEqual(["components/ui/nx-list.tsx"]);
  });

  // V22 decisions #9: a tile holds at most one cam row, so a screen file uses `next` or `pick` at most once.
  it("V22: a screen file uses the next/pick variant at most once", () => {
    const over = UI.filter((f) => !f.endsWith("nx-list.tsx") && !f.startsWith(path.join("app", "design-preview")) && !f.startsWith(path.join("components", "landing")))
      .map((f) => [f, (read(f).match(NX_VARIANT) ?? []).length] as const)
      .filter(([, n]) => n > 1)
      .map(([f]) => f.replaceAll("\\", "/"));
    // The landing draws one tile per section; its rows are data-driven (one `next` entry in TOC).
    expect(over).toEqual([]);
  });

  // UI-1a: one left edge. A page is drawn in PageColumn (mr-auto), never in its own centred
  // `mx-auto max-w-*`. Focus screens (FocusShell, the review and study session) keep their centred column
  // (DESIGN §5.2, §5.3), as does AuthShell; shells.tsx holds both frames and the shared container.
  it("UI-1a: no page centres its own column (mx-auto max-w-*)", () => {
    const CENTRED = new Set([
      path.join("components", "shells.tsx"),
      path.join("components", "session-study", "session-screen.tsx"),
      // The answer box keeps its centred column: it is drawn inside the focus frames (practice-live, review).
      path.join("components", "practice", "practice-answer.tsx"),
    ]);
    const pages = UI.filter(
      (f) =>
        !CENTRED.has(f) &&
        !f.startsWith(path.join("app", "design-preview")) &&
        !f.startsWith(path.join("components", "review")),
    );
    expect(pages.length).toBeGreaterThan(20);
    expect(offenders(pages, /mx-auto[^"'`]*max-w-|max-w-[^"'`]*mx-auto/)).toEqual([]);
  });

  it("the next/pick rule catches a violation (self-check)", () => {
    const two = '<NxRow next>a</NxRow><NxKind pick>b</NxKind><NxRow>c</NxRow>';
    expect((two.match(NX_VARIANT) ?? []).length).toBe(2);
    expect(("<NxRow>a</NxRow>".match(NX_VARIANT) ?? []).length).toBe(0);
  });

  // UI-A (user 05/11): an action is a pill, never underlined text. Links stay underlined only inside a sentence.
  it("UI-A: no underline on a button, summary or link that is an action", () => {
    const SENTENCE = new Set([
      path.join("components", "auth", "fields.tsx"),
      path.join("components", "documents", "document-list.tsx"),
      path.join("components", "practice", "practice-extras.tsx"),
      path.join("components", "practice", "practice-screen.tsx"),
    ]);
    const files = UI.filter((f) => !SENTENCE.has(f) && !f.startsWith(path.join("app", "design-preview")));
    expect(offenders(files, /<(a|button|summary|Link)\b[^>]*(?<![-\w])underline(?![-\w])/)).toEqual([]);
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

  it("components merge classes with lib/utils' cn, which knows the type steps (Tester, da48854)", () => {
    expect(offenders([...UI, ...files("lib", /\.ts$/)].filter((f) => !f.endsWith("utils.ts")), /from "cn(\/[\w-]+)?"/)).toEqual([]);
  });

  it("cn knows every type step declared in globals.css, so a new step cannot drop a colour", () => {
    const declared = [...GLOBALS.matchAll(/--text-([\w-]+):/g)]
      .map((m) => m[1])
      .filter((name) => !name.includes("--"));
    expect([...new Set(declared)].sort()).toEqual([...TYPE_STEPS].sort());
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

  // UI-1b (direction rule 3): a card has a hairline OR a shadow, never both; a sheet on the cover has
  // no shadow; there is no dog-ear; the highlighter is for first-level titles (and quoted evidence).
  it("UI-1b: no class list draws a border or ring and a shadow together", () => {
    const BORDER = /(^|[\s"'`])(border|border-\d|inset-ring|inset-ring-\d(\.\d)?|ring|ring-\d)(?=[\s"'`])/;
    const SHADOW = /(^|[\s"'`:])shadow-(?!none)/;
    const both = UI.filter((f) => !f.startsWith(path.join("app", "design-preview"))).flatMap((file) =>
      read(file)
        .split("\n")
        .flatMap((line, i) => (BORDER.test(line) && SHADOW.test(line) ? [`${file}:${i + 1}: ${line.trim()}`] : [])),
    );
    expect(both).toEqual([]);
  });

  it("UI-1b: the label sheet on the cover has a hairline and no box-shadow", () => {
    const css = read(path.join("components", "notebook", "notebook.module.css"));
    const label = /\.label \{([^}]*)\}/.exec(css)?.[1] ?? "";
    expect(label).toMatch(/border:\s*1px solid/);
    expect(label).not.toMatch(/box-shadow/);
  });

  it("UI-1b: no dog-ear (PageFold, motif-fold) anywhere", () => {
    expect(offenders(UI, /PageFold|motif-fold|data-motif="fold"/)).toEqual([]);
    expect(GLOBALS).not.toMatch(/motif-fold/);
  });

  it("UI-1b: <Marker> sits in an <h1>, or on quoted evidence (<q>)", () => {
    const outside = UI.filter((f) => !f.startsWith(path.join("app", "design-preview"))).flatMap((file) => {
      const lines = read(file).split("\n");
      return lines.flatMap((line, i) => {
        if (!line.includes("<Marker>")) return [];
        const before = lines.slice(Math.max(0, i - 3), i + 1).join("\n");
        return /<h1|<q /.test(before) ? [] : [`${file}:${i + 1}`];
      });
    });
    expect(outside).toEqual([]);
  });

  it("UI-1b: a secondary Start button is never larger than the primary (md); lg is for the pink tile", () => {
    const src = read(path.join("components", "today", "start-button.tsx"));
    expect(src).toMatch(/size=\{variant === "secondary" \? "md" : "lg"\}/);
  });

  it("a declaration inside a longer name does not count (review of 2ab0d91)", () => {
    expect(declaresItself("x--strong: #000;", "--strong")).toBe(false);
    expect(declaresItself("--strong-line: #000;", "--strong")).toBe(false);
    expect(declaresItself("[--strong:4px]", "--strong")).toBe(true);
  });
});
