// Edge cases of the core components, account fields, motifs and shells that components.test.ts,
// notebook-auth.test.ts, motifs.test.ts and shells.test.ts leave open (independent test pass).
// Each test names the change in src that turns it red.
import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AuthCard } from "@/components/auth/auth-card";
import { AuthField, AuthNote, PasswordField } from "@/components/auth/fields";
import { AppShell } from "@/components/shells";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const html = (node: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(node);

describe("Input: edges", () => {
  const classes = () => /class="([^"]+)"/.exec(html(h(Input, { name: "email" })))?.[1] ?? "";

  // Red when: `focus-visible:outline-offset-2` is dropped: the ring would touch the border.
  it("the focus ring is 2px away from the box", () => {
    expect(classes()).toMatch(/focus-visible:outline-offset-2/);
  });

  // Red when: the invalid border loses `aria-invalid:border-2`: 1px partial vs 1px line-strong is
  // too weak a signal on its own (final §4.2: 2px).
  it("an invalid field's border grows to 2px as well as changing colour", () => {
    expect(classes()).toMatch(/aria-invalid:border-2/);
  });

  // Red when: the fill turns `bg-transparent`: a box straight on the dark cover is 2.55:1.
  it("is filled with the sheet, so it never sits bare on the cover", () => {
    expect(classes()).toMatch(/\bbg-sheet\b/);
    expect(classes()).not.toMatch(/bg-transparent/);
  });

  // Red when: a caller's className no longer wins/merges (cn dropped): PasswordField's room for the eye.
  it("merges a caller's class", () => {
    expect(html(h(Input, { className: "pr-13" }))).toMatch(/\bpr-13\b/);
  });
});

describe("Button: edges", () => {
  // Red when: `focusableWhenDisabled` becomes `pending` alone: a button disabled by its caller
  // (rate limit) that is also pending would be aria-disabled, not disabled.
  it("pending AND disabled by the caller is disabled for real", () => {
    const markup = html(h(Button, { pending: true, disabled: true }, "Gửi"));
    expect(markup).toMatch(/\sdisabled=""/);
    expect(markup).toContain('aria-busy="true"');
  });

  // Red when: the spinner loses aria-hidden: a screen reader reads an empty element.
  it("the spinner is decoration", () => {
    expect(html(h(Button, { pending: true }, "Gửi"))).toMatch(/<span aria-hidden="true"[^>]*animate-spin/);
  });

  // Red when: a button that is not pending still renders a spinner or aria-busy.
  it("an idle button has no spinner, no aria-busy, no aria-disabled", () => {
    const markup = html(h(Button, {}, "Gửi"));
    expect(markup).not.toMatch(/animate-spin|\saria-busy=|\saria-disabled=/);
  });

  // Red when: a compound variant is dropped or its height edited (§4.1: 52 / 60 pill; the quiet
  // button keeps a 44px touch target).
  it.each([
    [{ variant: "primary-inverse" as const }, /\bh-15\b/],
    [{ variant: "secondary" as const, size: "lg" as const }, /\bh-15\b/],
    [{ variant: "secondary" as const }, /\bh-13\b/],
    [{ variant: "quiet" as const }, /\bh-11\b/],
  ])("%j has its height", (options, height) => {
    expect(buttonVariants(options)).toMatch(height);
  });

  // Red when: the inverse label colour is written `text-(--inverse-fg)`, which Tailwind reads as
  // a font size (primary-inverse lost its label this way): it needs the `color:` type.
  it("primary-inverse names the type of both custom-property colours", () => {
    const classes = buttonVariants({ variant: "primary-inverse" });
    expect(classes).toMatch(/\bbg-\(color:--inverse-bg\)/);
    expect(classes).toMatch(/\btext-\(color:--inverse-fg\)/);
  });
});

describe("account fields: edges", () => {
  const password = () =>
    html(h(PasswordField, { id: "password", label: "Mật khẩu", name: "password", autoComplete: "current-password" }));

  // Red when: the eye button loses type="button": pressing it would submit the login form.
  it("the eye is a button that does not submit", () => {
    expect(password()).toMatch(/<button type="button"[^>]*aria-label="Hiện mật khẩu"/);
  });

  // Red when: the eye icon loses aria-hidden.
  it("the eye's icon is decoration", () => {
    expect(password()).toMatch(/<svg[^>]*aria-hidden="true"/);
  });

  // Red when: `{...props}` stops reaching the input (name or autoComplete lost: a password
  // manager and FormData would see nothing).
  it("name and autoComplete reach the input, not the wrapper", () => {
    expect(password()).toMatch(/<input[^>]*name="password"/);
    expect(password()).toMatch(/<input[^>]*autoComplete="current-password"/);
    expect(password()).not.toMatch(/<div[^>]*name=/);
  });

  // Red when: the label loses htmlFor: the field has no accessible name.
  it("the label points at the input", () => {
    expect(password()).toMatch(/<label[^>]*for="password"/);
    expect(password()).toMatch(/<input[^>]*id="password"/);
  });

  // Red when: describedBy/invalid are dropped from a field that is NOT invalid: nothing to emit.
  it("a valid field has no aria-invalid and no stray aria-describedby", () => {
    const markup = html(h(AuthField, { id: "email", label: "Email", name: "email" }));
    expect(markup).not.toMatch(/\saria-invalid=|\saria-describedby=/);
  });

  // Red when: invalid={false} is rendered as aria-invalid="false"/"true" by mistake.
  it("invalid={false} omits aria-invalid", () => {
    expect(html(h(AuthField, { id: "e", label: "E", invalid: false }))).not.toMatch(/\saria-invalid=/);
  });

  // Red when: role="alert" is dropped: the rate-limit note would not be announced.
  it("AuthNote is an alert with a decorative icon", () => {
    const markup = html(h(AuthNote, null, "Thử lại sau 5 phút."));
    expect(markup).toMatch(/<p role="alert"/);
    expect(markup).toMatch(/<svg[^>]*aria-hidden="true"/);
  });
});

describe("account screen motifs: edges", () => {
  const markup = () => html(h(AuthCard, { title: "Đăng nhập", children: "form" }));

  // Red when: a third grid corner, a second fold or a second sticker is added: §4.10 rules
  // (two opposite corners, one sticker per screen).
  it("exactly two grids, one fold, one sticker", () => {
    expect(markup().match(/data-motif="grid"/g)).toHaveLength(2);
    expect(markup().match(/data-motif="fold"/g)).toHaveLength(1);
    expect(markup().match(/data-motif="sticker"/g)).toHaveLength(1);
  });

  // Red when: every decorative element loses aria-hidden: count the motifs and their hidden flag together.
  it("every motif and the sticker's icon are hidden from assistive tech", () => {
    const motifs = markup().match(/<span[^>]*data-motif="[^"]+"[^>]*>/g) ?? [];
    expect(motifs).toHaveLength(4);
    for (const tag of motifs) expect(tag).toContain('aria-hidden="true"');
    expect(markup()).toMatch(/<svg[^>]*aria-hidden="true"/);
  });

  // Red when: the card wrapper loses `relative z-1`: the grid (z-0, absolute) paints over the form.
  it("the card sits above the grid", () => {
    expect(markup()).toMatch(/class="relative z-1 w-full max-w-\[520px\]"/);
  });

  // Red when: the motifs move inside the title row or the form: motifs must not sit behind text.
  it("no motif is inside the heading", () => {
    expect(markup()).not.toMatch(/<h1[^>]*>(?:(?!<\/h1>).)*data-motif/);
  });
});

describe("shells: edges", () => {
  const shell = () => html(h(AppShell, { current: "/today", children: "x" }));

  // Red when: aria-current is dropped: the current page is only inverted ink (colour alone).
  it("marks only the current item with aria-current=page", () => {
    expect(shell().match(/aria-current="page"/g)).toHaveLength(1);
    expect(shell()).toMatch(/<a href="\/today" aria-current="page"/);
  });

  // Red when: no item is current but one is marked anyway, or the current prop is ignored.
  it("no current page, no aria-current", () => {
    expect(html(h(AppShell, { children: "x" }))).not.toMatch(/aria-current/);
  });

  // Red when: the nav loses its name: two landmarks of the page would be indistinguishable.
  it("the navigation is a named landmark", () => {
    expect(shell()).toMatch(/<nav aria-label="Chính"/);
  });

  // Red when: nav items get under 40px high (touch target, final §5).
  it("nav items are at least 40px high pills", () => {
    expect(shell()).toMatch(/<a [^>]*class="[^"]*\bh-10\b[^"]*\brounded-full\b/);
  });
});
