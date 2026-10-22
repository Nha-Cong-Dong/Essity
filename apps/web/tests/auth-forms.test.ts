// The account forms of PR #9 after the restyle (plan "Auth của #9 không vỡ"): the attributes a
// browser, a password manager and a screen reader depend on, read from the static render.
import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CheckEmailActions } from "@/components/auth/check-email-actions";
import { ForgotPassword } from "@/components/auth/forgot-password";
import { LoginForm } from "@/components/auth/login-form";
import { RegisterForm } from "@/components/auth/register-form";

const render = (node: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(node);
const input = (markup: string, name: string) =>
  [...markup.matchAll(/<input[^>]*>/g)].map((m) => m[0]).find((tag) => tag.includes(`name="${name}"`)) ?? "";

/** Every id an aria-describedby points at must exist in the same markup. */
function danglingDescriptions(markup: string): string[] {
  return [...markup.matchAll(/aria-describedby="([^"]+)"/g)]
    .flatMap((m) => m[1].split(" "))
    .filter((id) => !markup.includes(`id="${id}"`));
}

describe("LoginForm", () => {
  const markup = () => render(h(LoginForm));

  // Red when: name/type/autoComplete/required of a field changes (password managers, FormData read).
  it("email and password keep name, type, autocomplete, required", () => {
    expect(input(markup(), "email")).toMatch(/type="email"/);
    expect(input(markup(), "email")).toMatch(/autoComplete="email"/);
    expect(input(markup(), "email")).toMatch(/required=""/);
    expect(input(markup(), "password")).toMatch(/type="password"/);
    expect(input(markup(), "password")).toMatch(/autoComplete="current-password"/);
    expect(input(markup(), "password")).toMatch(/required=""/);
  });

  // Red when: noValidate is dropped (the browser's English bubble replaces the Vietnamese errors).
  it("is a no-validate form with one submit button, idle at first", () => {
    expect(markup()).toMatch(/<form[^>]*noValidate=""/);
    expect(markup().match(/type="submit"/g)).toHaveLength(1);
    expect(markup()).not.toMatch(/\saria-busy=|\saria-disabled=|\sdisabled=""/);
  });

  // Red when: labels lose their for/id pairs.
  it("each field has a label that points at it", () => {
    expect(markup()).toMatch(/<label[^>]*for="email"/);
    expect(markup()).toMatch(/<label[^>]*for="password"/);
    expect(input(markup(), "email")).toMatch(/id="email"/);
    expect(input(markup(), "password")).toMatch(/id="password"/);
  });

  // Red when: the submit button gets a class height again (h-14 over the size scale).
  it("the submit button is full width and takes its height from the size scale", () => {
    const button = /<button[^>]*type="submit"[^>]*>/.exec(markup())?.[0] ?? "";
    expect(button).toMatch(/\bw-full\b/);
    expect(button).toMatch(/\bh-13\b/);
    expect(button).not.toMatch(/\bh-14\b/);
  });

  // Red when: no description at all is rendered while idle, or one points at a missing id.
  it("has no dangling aria-describedby", () => {
    expect(danglingDescriptions(markup())).toEqual([]);
  });
});

describe("RegisterForm", () => {
  const markup = () => render(h(RegisterForm));

  // Red when: the new-password autocomplete is lost: managers would offer the saved password.
  it("password asks for a new one; email is an email", () => {
    expect(input(markup(), "password")).toMatch(/autoComplete="new-password"/);
    expect(input(markup(), "email")).toMatch(/autoComplete="email"/);
    expect(input(markup(), "email")).toMatch(/type="email"/);
  });

  // Red when: the hint id and the field's describedBy drift apart.
  it("the password is described by its hint, and the hint exists", () => {
    expect(input(markup(), "password")).toMatch(/aria-describedby="password-hint"/);
    expect(markup()).toMatch(/<p id="password-hint"/);
    expect(danglingDescriptions(markup())).toEqual([]);
  });

  // Red when: noValidate is dropped from the sign-up form (browser bubbles replace our errors).
  it("is a no-validate form", () => {
    expect(markup()).toMatch(/<form[^>]*noValidate=""/);
  });

  // Red when: an idle form is rendered invalid.
  it("starts valid and idle", () => {
    expect(markup()).not.toMatch(/\saria-invalid=|\saria-busy=|\saria-disabled=/);
  });
});

describe("ForgotPassword", () => {
  const markup = () => render(h(ForgotPassword));

  // Red when: the field's attributes change.
  it("asks for an email with autocomplete", () => {
    expect(input(markup(), "email")).toMatch(/type="email"/);
    expect(input(markup(), "email")).toMatch(/autoComplete="email"/);
    expect(input(markup(), "email")).toMatch(/required=""/);
  });

  // Red when: noValidate is dropped from the forgot-password form.
  it("is a no-validate form", () => {
    expect(markup()).toMatch(/<form[^>]*noValidate=""/);
  });

  it("has one submit button and a way back to login", () => {
    expect(markup().match(/type="submit"/g)).toHaveLength(1);
    expect(markup()).toMatch(/href="\/login"/);
  });
});

describe("CheckEmailActions", () => {
  // Red when: the countdown button turns into a pending one at rest, or loses its real disabled.
  it("while counting down the resend button is really disabled, not busy", () => {
    const markup = render(h(CheckEmailActions, { initialWait: 42 }));
    expect(markup).toContain("Gửi lại (0:42)");
    expect(markup).toMatch(/<button[^>]*\sdisabled=""[^>]*>/);
    expect(markup).not.toMatch(/aria-busy/);
  });

  it("at 0 the resend button can be pressed", () => {
    const markup = render(h(CheckEmailActions, { initialWait: 0 }));
    const button = /<button[^>]*>(?:(?!<\/button>).)*Gửi lại<\/button>/.exec(markup)?.[0] ?? "";
    expect(button).not.toMatch(/\sdisabled=|\saria-disabled=/);
  });

  // Red when: the live region is dropped (the "Đã gửi lại." message would not be announced).
  it("keeps its polite live region", () => {
    expect(render(h(CheckEmailActions, { initialWait: 0 }))).toMatch(/aria-live="polite"/);
  });
});
