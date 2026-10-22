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

describe("password field (review of 7bcc5d7)", () => {
  const markup = () =>
    renderToStaticMarkup(
      h(PasswordField, {
        id: "password",
        label: "Mật khẩu",
        name: "password",
        describedBy: "password-error",
        invalid: true,
        autoComplete: "new-password",
        className: "tracking-wide",
      }),
    );

  it("keeps its label, description, invalid state, autocomplete and type", () => {
    expect(markup()).toMatch(/<label[^>]*for="password"/);
    expect(markup()).toContain('aria-describedby="password-error"');
    expect(markup()).toContain('aria-invalid="true"');
    expect(markup()).toContain('autoComplete="new-password"');
    expect(markup()).toContain('type="password"');
  });

  it("a caller's class does not drop the room kept for the eye", () => {
    expect(markup()).toMatch(/<input[^>]*class="[^"]*\bpr-13\b[^"]*\btracking-wide\b/);
  });

  it("the eye has one fixed name and says its state with aria-pressed", () => {
    expect(markup()).toContain('aria-label="Hiện mật khẩu"');
    expect(markup()).toContain('aria-pressed="false"');
  });
});

describe("notebook cover at level b (§4.4, §4.5)", () => {
  const cover = () => renderToStaticMarkup(h(NotebookCover, { title: "Đăng nhập", children: h(NhanVo, { children: "x" }) }));

  // R10 (T1.21, plan D16): what the cover is, not a list of strings an older design used.
  it("keeps the spine and one stripe", () => {
    expect(cover().match(/<i><\/i>/g) ?? []).toHaveLength(1);
  });

  it("is rounded 10 on the spine side and 28 on the edge", () => {
    expect(CSS).toMatch(/border-radius: var\(--radius-cover-spine\) var\(--radius-cover-edge\) var\(--radius-cover-edge\) var\(--radius-cover-spine\)/);
  });

  it("the title uses the display step", () => {
    expect(CSS).toMatch(/font-size: var\(--text-display\)/);
  });

  it("the label values are ink", () => {
    const value = /\.rowValue \{[^}]*\}/.exec(CSS)?.[0] ?? "";
    expect(value).toMatch(/color: var\(--ink\)/);
  });
});
