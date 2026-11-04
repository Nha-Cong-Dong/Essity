// `cn` (package "cn", a tailwind-merge stand-in) treats every `text-<name>` as one group, so a
// type step (`text-read`, `text-body`) silently removes a text colour next to it, and the other
// way round. These tests read the classes a component really renders, after the merge.
import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const classesOf = (node: Parameters<typeof renderToStaticMarkup>[0]) =>
  (/class="([^"]+)"/.exec(renderToStaticMarkup(node))?.[1] ?? "").split(/\s+/);

describe("a text colour survives next to a type step (after cn)", () => {
  // Red today: compound variant `text-read` removes `text-on-hong`; the label falls back to the
  // inherited ink colour on the pink fill (about 2.3:1 in light mode). Green when `cn` knows the
  // type steps (extend its config) or the size is written as `text-(length:--text-read)`.
  it("primary lg keeps text-on-hong and the 18px step", () => {
    const classes = classesOf(h(Button, { size: "lg" }, "Bắt đầu"));
    expect(classes).toContain("text-on-hong");
    expect(classes).toContain("text-read");
  });

  // Red today: `text-read` removes `text-(color:--inverse-fg)`; on the light pink tile the label
  // inherits white onto the white `--inverse-bg` button (invisible).
  it.each(["md", "lg"] as const)("primary-inverse %s keeps its label colour and the 18px step", (size) => {
    const classes = classesOf(h(Button, { variant: "primary-inverse", size }, "Bắt đầu"));
    expect(classes).toContain("text-(color:--inverse-fg)");
    expect(classes).toContain("text-read");
  });

  // Red today: `text-ink` removes `text-body`; the field's size is only inherited from <body>
  // (a field inside a `text-meta` block would shrink below 16px, where iOS zooms on focus).
  it("Input keeps its 16px step beside its ink colour", () => {
    const classes = classesOf(h(Input, {}));
    expect(classes).toContain("text-ink");
    expect(classes).toContain("text-body");
  });

  // Red today for the same reason on the base class (`text-body` lost next to `text-on-hong`).
  it("primary md keeps the 16px step beside its label colour", () => {
    const classes = classesOf(h(Button, {}, "Gửi"));
    expect(classes).toContain("text-on-hong");
    expect(classes).toContain("text-body");
  });
});
