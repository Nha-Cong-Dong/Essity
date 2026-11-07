// @vitest-environment jsdom
// C1-AUTH-SUB-V4: the result states of the four secondary account screens share one block
// (round mark, one bold line, explanation, actions) and each page gives the plum field a greeting
// and a bubble, like /login and /register. Behaviour (texts, links, roles) stays as it was.
import { cleanup, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { AuthBody, AuthState } from "@/components/auth/auth-state";

afterEach(cleanup);

describe("AuthState", () => {
  it("draws the mark, the bold line, the body and the actions in that order", () => {
    const { container } = render(
      <AuthState mark="ok" role="status" title="Đã xong." actions={<a href="/login">Đăng nhập</a>}>
        <AuthBody>Mô tả.</AuthBody>
      </AuthState>,
    );
    const status = screen.getByRole("status");
    const kids = Array.from(status.children).map((el) => el.textContent);
    expect(kids).toEqual(["", "Đã xong.", "Mô tả.", "Đăng nhập"]);
    expect(container.querySelector('[data-auth-mark="ok"]')?.getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByRole("link", { name: "Đăng nhập" }).getAttribute("href")).toBe("/login");
  });

  it("uses the success tone only for ok; a problem is never red", () => {
    const { container } = render(
      <>
        <AuthState mark="ok" title="a" />
        <AuthState mark="expired" title="b" />
        <AuthState mark="warn" title="c" />
        <AuthState mark="mail" title="d" />
      </>,
    );
    const marks = Array.from(container.querySelectorAll("[data-auth-mark]"));
    expect(marks.map((m) => m.className.includes("text-correct"))).toEqual([true, false, false, false]);
    expect(marks.every((m) => !/red|danger|wrong/.test(m.className))).toBe(true);
  });
});

describe("secondary account pages", () => {
  const read = (path: string) => readFileSync(join(__dirname, "..", path), "utf8");
  it.each(["app/check-email/page.tsx", "app/verify-email/page.tsx", "app/reset-password/page.tsx"])(
    "%s gives the field a greeting and a bubble",
    (path) => {
      const source = read(path);
      expect(source).toMatch(/greeting=/);
      expect(source).toMatch(/bubble="[^"]+"/);
    },
  );
  it("forgot-password gives both of its views a greeting and a bubble", () => {
    const source = read("components/auth/forgot-password.tsx");
    expect(source.match(/<AuthLayout[^>]*greeting=\{GREETING\}[^>]*bubble=/g)).toHaveLength(2);
  });
});
