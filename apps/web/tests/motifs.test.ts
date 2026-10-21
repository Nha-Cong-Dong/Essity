// Motifs (design system v3.1 §4.10; plan V5, V7): decoration only, never information. Rendered to
// static markup and read from globals.css.
import { readFileSync } from "node:fs";
import path from "node:path";

import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AuthCard } from "@/components/auth/auth-card";
import { GridCorner, PageFold, Sticker } from "@/components/motifs";

const CSS = readFileSync(path.resolve(import.meta.dirname, "../app/globals.css"), "utf-8");
const rule = (selector: string) => new RegExp(`${selector.replace(/[.[\]()]/g, "\\$&")}\\s*\\{([^}]*)\\}`).exec(CSS)?.[1] ?? "";

describe("motifs are decoration (§4.10 rule 7)", () => {
  it.each([
    ["GridCorner", h(GridCorner, { corner: "tl" })],
    ["PageFold", h(PageFold)],
    ["Sticker", h(Sticker, { icon: "pen" })],
  ])("%s is hidden from assistive tech", (_, node) => {
    const markup = renderToStaticMarkup(node);
    expect(markup).toMatch(/^<[a-z]+[^>]*aria-hidden="true"/);
    expect(markup).not.toMatch(/<title|alt=/);
  });

  it("a sticker's icon is not focusable and has no id to collide", () => {
    const markup = renderToStaticMarkup(h(Sticker, { icon: "pen" }));
    expect(markup).toMatch(/<svg[^>]*focusable="false"/);
    expect(markup).not.toMatch(/\bid="/);
  });

  it("every motif class ignores the pointer, and print drops them", () => {
    expect(rule(".motif")).toMatch(/pointer-events:\s*none/);
    expect(rule(".sticker")).toMatch(/pointer-events:\s*none/);
    expect(CSS).toMatch(/@media print\s*\{\s*\.motif,\s*\.sticker\s*\{\s*display:\s*none/);
  });

  it("they float slowly, and stand still when motion is reduced", () => {
    expect(CSS).toMatch(/@media \(prefers-reduced-motion: no-preference\)\s*\{[^}]*\.motif-float\s*\{\s*animation:/);
    expect(CSS).toMatch(/@keyframes motif-float/);
  });

  it("live in the components layer, so a class passed to a motif wins (review of 940760e)", () => {
    const layer = CSS.slice(CSS.indexOf("@layer components {"));
    expect(layer).toMatch(/^@layer components \{\s*\.motif \{/);
    expect(layer).toContain(".sticker {");
  });

  it("the folded corner shows the surface under the sheet, the cover by default (review of 940760e)", () => {
    expect(CSS).toMatch(/--fold-under: var\(--cover\)/);
    expect(CSS).toMatch(/linear-gradient\(225deg, var\(--fold-under\)/);
  });

  it("the background grid is hidden on narrow screens (§4.10 rule 5)", () => {
    expect(CSS).toMatch(/@media \(max-width: 900px\)\s*\{\s*\.motif-wide\s*\{\s*display:\s*none/);
    expect(renderToStaticMarkup(h(GridCorner, { corner: "br" }))).toMatch(/motif-wide/);
  });
});

describe("account screens (§4.10 rule 3)", () => {
  const markup = () => renderToStaticMarkup(h(AuthCard, { title: "Đăng nhập", children: "form" }));

  it("carry the grid in two opposite corners, a page fold and the pen sticker: three motifs", () => {
    // The grid in two corners counts as the one background motif.
    const kinds = new Set(markup().match(/data-motif="[^"]+"/g) ?? []);
    expect([...kinds].sort()).toEqual(['data-motif="fold"', 'data-motif="grid"', 'data-motif="sticker"']);
    expect(markup()).toMatch(/motif-grid[^"]*\btl\b/);
    expect(markup()).toMatch(/motif-grid[^"]*\bbr\b/);
  });
});
