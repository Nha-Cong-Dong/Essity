// One page container for header and content (design system v3.1 §5, §7 #1–5): rendered to
// static markup, plus the account menu's surfaces read from its source.
import { readFileSync } from "node:fs";
import path from "node:path";

import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppShell, AuthShell, FocusShell } from "@/components/shells";

const CONTAINER = /max-w-\(--page-max\)[^"]*px-\(--page-gutter\)|px-\(--page-gutter\)[^"]*max-w-\(--page-max\)/;
const containers = (markup: string) =>
  [...markup.matchAll(/class="([^"]+)"/g)].map((m) => m[1]).filter((c) => CONTAINER.test(c));

describe("frames share one container (§5)", () => {
  it("AppShell: header and main start at the same left edge", () => {
    const markup = renderToStaticMarkup(h(AppShell, { current: "/today", children: "x" }));
    expect(containers(markup)).toHaveLength(2);
  });

  it("FocusShell and AuthShell too", () => {
    const focus = renderToStaticMarkup(
      h(FocusShell, { position: 3, total: 14, exit: h("a", { href: "/today" }, "Dừng tại đây"), children: "x" }),
    );
    const auth = renderToStaticMarkup(h(AuthShell, { children: "x" }));
    expect(containers(focus)).toHaveLength(2);
    expect(containers(auth)).toHaveLength(2);
  });

  it("AppShell header is 64px; the current nav item is inverted ink; the logo uses the logo step", () => {
    const markup = renderToStaticMarkup(h(AppShell, { current: "/today", children: "x" }));
    expect(markup).toMatch(/h-\(--header-h\)/);
    expect(markup).toMatch(/aria-\[current=page\]:bg-ink/);
    expect(markup).toMatch(/aria-\[current=page\]:text-bg/);
    expect(markup).toMatch(/text-logo/);
  });

  it("FocusShell header is 56px, its bar 3px, nothing wraps", () => {
    const markup = renderToStaticMarkup(
      h(FocusShell, { position: 3, total: 14, exit: h("a", { href: "/today" }, "Dừng tại đây"), children: "x" }),
    );
    expect(markup).toMatch(/h-\(--header-focus-h\)/);
    expect(markup).toMatch(/h-\[3px\]/);
    expect(markup).toMatch(/whitespace-nowrap/);
    expect(markup).toContain("Câu 3 / 14");
  });

  it("the nav can shrink and scroll rather than push the page sideways at 320px (review of 96bebab)", () => {
    const markup = renderToStaticMarkup(h(AppShell, { current: "/today", children: "x" }));
    expect(markup).toMatch(/<nav[^>]*class="[^"]*min-w-0[^"]*overflow-x-auto/);
  });

  it("the sticky header never hides the focused element (WCAG 2.4.11, review of 96bebab)", () => {
    const css = readFileSync(path.resolve(import.meta.dirname, "../app/globals.css"), "utf-8");
    expect(css).toMatch(/scroll-padding-top: calc\(var\(--header-h\) \+ 8px\)/);
  });

  it("shells and the account menu use type steps and role radii, not pixel values", () => {
    for (const file of ["components/shells.tsx", "components/account-menu.tsx"]) {
      const source = readFileSync(path.resolve(import.meta.dirname, "..", file), "utf-8");
      expect(source, file).not.toMatch(/text-\[\d+px\]|rounded-\[|rounded-2xl/);
    }
  });

  it("the account menu is a raised sheet; its button a 40px rose circle", () => {
    const source = readFileSync(path.resolve(import.meta.dirname, "../components/account-menu.tsx"), "utf-8");
    expect(source).toMatch(/rounded-sheet[^"]*bg-raised[^"]*shadow-over/);
    expect(source).toMatch(/size-10[^"]*rounded-full[^"]*bg-rose-100/);
  });
});
