// @vitest-environment jsdom
// Behaviour tests for client components run in jsdom, one file at a time (docblock above); the rest
// of the suite stays in Node. This file proves the setup: a click changes what the user sees.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PasswordField } from "@/components/auth/fields";

afterEach(cleanup); // vitest `globals` is off, so Testing Library cannot clean up by itself

describe("jsdom setup", () => {
  // Red when: .tsx tests are not collected, or the environment is not a DOM.
  it("pressing the eye shows the password", () => {
    render(<PasswordField id="password" label="Mật khẩu" name="password" />);
    const input = screen.getByLabelText("Mật khẩu");
    expect(input.getAttribute("type")).toBe("password");

    fireEvent.click(screen.getByRole("button", { name: "Hiện mật khẩu" }));

    expect(input.getAttribute("type")).toBe("text");
  });
});
