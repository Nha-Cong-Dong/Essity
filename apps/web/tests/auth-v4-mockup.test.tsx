// @vitest-environment jsdom
// AUTH-V4: login and register match the v4 mockups (headline underline, sticker chain, tinted
// fields, "Quên mật khẩu?" as a pink text link).
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AuthLayout, Underlined } from "@/components/auth/auth-layout";
import { LoginForm } from "@/components/auth/login-form";

afterEach(cleanup);

describe("AUTH-V4 mockup match", () => {
  it("'Quên mật khẩu?' is a pink text link, not a pill; inputs are hong-tint filled", () => {
    const { container } = render(<LoginForm />);
    const link = screen.getByRole("link", { name: "Quên mật khẩu?" });
    expect(link.className).not.toContain("inset-ring");
    expect(link.className).toContain("text-hong-text");
    expect(link.className).toContain("min-h-11");
    expect(container.querySelector("#identifier")?.className).toContain("bg-hong-tint");
    expect(container.querySelector("#password")?.className).toContain("bg-hong-tint");
  });

  it("the layout underlines the accent words of the headline and draws the sticker chain", () => {
    const { container } = render(
      <AuthLayout
        title="T"
        greeting={
          <>
            <span>x</span> <span>
              <Underlined>gặp bạn</Underlined>
            </span>
          </>
        }
        bubble="b"
      >
        <p>c</p>
      </AuthLayout>,
    );
    expect(container.querySelector("em svg path")).toBeTruthy();
    expect(container.querySelectorAll("svg[data-sticker]").length).toBe(4);
    expect(container.querySelector("svg[data-arrow]")).toBeTruthy();
  });
});
