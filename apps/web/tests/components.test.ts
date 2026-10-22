// Core components of design system v3.1 (docs/plans/design-architecture-final.md §4.1–4.3),
// rendered to static markup in Node (plan V6): classes and attributes, not layout.
import { existsSync } from "node:fs";
import path from "node:path";

import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet } from "@/components/ui/sheet";

import { contrastOn, mixOklab, palette } from "./css-tokens";

const html = (node: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(node);
const VARIANTS = ["primary", "secondary", "quiet", "primary-inverse"] as const;

describe("Button (§4.1)", () => {
  it.each(["primary", "secondary", "primary-inverse"] as const)("%s is a pill", (variant) => {
    expect(buttonVariants({ variant })).toMatch(/\brounded-full\b/);
  });

  it.each(VARIANTS)("%s never fades a disabled button with opacity (§7 #11)", (variant) => {
    expect(buttonVariants({ variant })).not.toMatch(/opacity/);
  });

  it("a disabled primary is sunken with soft ink, and does not lift", () => {
    const classes = buttonVariants({ variant: "primary" });
    expect(classes).toMatch(/disabled:bg-sunken/);
    expect(classes).toMatch(/disabled:text-ink-soft/);
    expect(classes).toMatch(/disabled:translate-y-0/);
  });

  it("the secondary border is line-strong (3:1), drawn inside", () => {
    expect(buttonVariants({ variant: "secondary" })).toMatch(/inset-ring-line-strong/);
  });

  it("lg is 60px, md 52px", () => {
    expect(buttonVariants({ variant: "primary", size: "lg" })).toMatch(/\bh-15\b/);
    expect(buttonVariants({ variant: "primary" })).toMatch(/\bh-13\b/);
  });

  it("a pending button is busy, cannot be pressed twice, and keeps focus (review of 4b86dc4)", () => {
    const markup = html(h(Button, { pending: true }, "Gửi"));
    expect(markup).toContain('aria-busy="true"');
    expect(markup).toContain('aria-disabled="true"');
    expect(markup).not.toMatch(/\sdisabled=""/);
  });

  it("a button disabled by its caller (rate limit) is disabled for real", () => {
    expect(html(h(Button, { pending: false, disabled: true }, "Đăng nhập"))).toMatch(/\sdisabled=""/);
  });

  it("the hover colour is hồng 88% with ink, in oklab, and its label still reads (≥ 4.5)", () => {
    expect(buttonVariants({ variant: "primary" })).toContain("hover:bg-[color-mix(in_oklab,var(--hong)_88%,var(--ink))]");
    for (const mode of ["light", "dark"] as const) {
      const tokens = palette(mode);
      const hover = mixOklab(tokens, "--hong", 88, "--ink");
      expect(contrastOn(tokens, "--on-hong", hover)).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("the oklab mix is right on a known pair (white and black at 50%)", () => {
    expect(mixOklab({ "--w": "#ffffff", "--k": "#000000" }, "--w", 50, "--k")).toBe("#636363");
  });

  it("focus keeps the 3px offset ring", () => {
    expect(buttonVariants({ variant: "primary" })).toMatch(/focus-visible:outline-offset-3/);
  });
});

describe("Input (§4.2)", () => {
  const markup = () => html(h(Input, { name: "email" }));

  it("shows focus: no bare outline-none without a focus-visible outline (review plan #1)", () => {
    const classes = /class="([^"]+)"/.exec(markup())?.[1] ?? "";
    expect(classes).toMatch(/focus-visible:outline-2/);
    expect(classes).toMatch(/focus-visible:outline-focus/);
  });

  it("is a 52px box with the control radius and a line-strong border", () => {
    expect(markup()).toMatch(/\bh-13\b/);
    expect(markup()).toMatch(/\brounded-control\b/);
    expect(markup()).toMatch(/\bborder-line-strong\b/);
  });

  it("a disabled field is sunken, not faded", () => {
    expect(markup()).toMatch(/disabled:bg-sunken/);
    expect(markup()).not.toMatch(/opacity/);
  });

  it("an invalid field keeps the 2px partial border", () => {
    expect(markup()).toMatch(/aria-invalid:border-partial/);
  });
});

describe("Label", () => {
  it("never fades with opacity", () => {
    expect(html(h(Label, { htmlFor: "email" }, "Email"))).not.toMatch(/opacity/);
  });
});

describe("Sheet and Tile (§4.3)", () => {
  it.each([
    ["sheet", /rounded-sheet/, /shadow-sheet/],
    ["over", /rounded-sheet/, /shadow-over/],
    ["sunken", /rounded-sheet/, /bg-sunken/],
    ["tile", /rounded-tile/, /shadow-sheet/],
  ] as const)("%s", (variant, radius, surface) => {
    const markup = html(h(Sheet, { variant }, "x"));
    expect(markup).toMatch(radius);
    expect(markup).toMatch(surface);
  });

  it("a pink tile is the solid pink surface", () => {
    expect(html(h(Sheet, { variant: "tile", tone: "hong" }, "x"))).toContain('data-surface="hong"');
  });

  it("a rose tile has no shadow until hovered", () => {
    const markup = html(h(Sheet, { variant: "tile", tone: "rose" }, "x"));
    expect(markup).toMatch(/bg-rose-100/);
    expect(markup).toMatch(/hover:shadow-sheet/);
  });

  it("Card is gone: Sheet replaces it", () => {
    expect(existsSync(path.resolve(import.meta.dirname, "../components/ui/card.tsx"))).toBe(false);
  });
});
