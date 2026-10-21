// Account fields as boxes (plan V4, final §4.2) and the notebook cover at level b (final §4.4,
// §4.5): rendered to static markup and read from the stylesheet.
import { readFileSync } from "node:fs";
import path from "node:path";

import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AuthField, PasswordField } from "@/components/auth/fields";
import { NhanVo, NotebookCover } from "@/components/notebook";

const CSS = readFileSync(path.resolve(import.meta.dirname, "../components/notebook/notebook.module.css"), "utf-8");

describe("account fields (V4)", () => {
  const field = () =>
    renderToStaticMarkup(
      h(AuthField, { id: "email", label: "Email", describedBy: "email-error", invalid: true, name: "email" }),
    );

  it("are boxes: the Input control radius and line-strong border, no dotted line", () => {
    expect(field()).toMatch(/rounded-control/);
    expect(field()).toMatch(/border-line-strong/);
    expect(field()).not.toMatch(/border-dotted/);
  });

  it("keep their label, description and invalid state for assistive tech", () => {
    expect(field()).toMatch(/<label[^>]*for="email"[^>]*>Email<\/label>/);
    expect(field()).toContain('aria-describedby="email-error"');
    expect(field()).toContain('aria-invalid="true"');
    expect(field()).toContain('name="email"');
  });

  it("show focus (review of the plan #1)", () => {
    expect(field()).toMatch(/focus-visible:outline-2/);
  });

  it("the password eye sits in a box of its own around the input, not at a guessed offset", () => {
    const markup = renderToStaticMarkup(h(PasswordField, { id: "password", label: "Mật khẩu", name: "password" }));
    expect(markup).not.toMatch(/top-\[\d+px\]/);
    expect(markup).toMatch(/<div class="relative[^"]*"><input[^>]*id="password"/);
    expect(markup).toMatch(/aria-label="Hiện mật khẩu"[^>]*class="[^"]*size-11/);
  });
});

describe("notebook cover at level b (§4.4, §4.5)", () => {
  const cover = () => renderToStaticMarkup(h(NotebookCover, { title: "Đăng nhập", children: h(NhanVo, { children: "x" }) }));

  it("keeps the spine and one stripe; drops the paper behind it", () => {
    expect(cover()).not.toMatch(/under/);
    expect(CSS).not.toMatch(/\.under\b/);
    expect(cover().match(/<i><\/i>/g) ?? []).toHaveLength(1);
  });

  it("has no texture, corner protectors, staples, second stripe, dashed frame or tape", () => {
    expect(CSS).not.toMatch(/\.board::(before|after)/);
    expect(CSS).not.toMatch(/\.spine::(before|after)/);
    expect(CSS).not.toMatch(/\.label::(before|after)/);
    expect(CSS).not.toMatch(/\.stripes i \+ i/);
    expect(CSS).not.toMatch(/background-size: 14px 14px/);
  });

  it("is rounded 10 on the spine side and 28 on the edge", () => {
    expect(CSS).toMatch(/border-radius: var\(--radius-cover-spine\) var\(--radius-cover-edge\) var\(--radius-cover-edge\) var\(--radius-cover-spine\)/);
  });

  it("the title uses the display step (line height 1.15), not a fixed 64px with line height 1", () => {
    expect(CSS).not.toMatch(/font-size: 64px/);
    expect(CSS).not.toMatch(/line-height: 1;/);
    expect(CSS).toMatch(/font-size: var\(--text-display\)/);
  });

  it("the label values are upright ink, not italic pink", () => {
    const value = /\.rowValue \{[^}]*\}/.exec(CSS)?.[0] ?? "";
    expect(value).not.toMatch(/italic/);
    expect(value).toMatch(/color: var\(--ink\)/);
  });
});
