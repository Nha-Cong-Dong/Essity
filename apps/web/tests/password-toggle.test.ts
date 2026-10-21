// The password eye, in its "shown" state. Static markup always renders the first state, so the
// hook is replaced for this file only: useState answers `true`.
import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react")>();
  return { ...actual, useState: () => [true, () => undefined] };
});

import { PasswordField } from "@/components/auth/fields";

describe("PasswordField shown", () => {
  const markup = () => renderToStaticMarkup(h(PasswordField, { id: "password", label: "Mật khẩu", name: "password" }));

  // Red when: the type stops following the state (`type="password"` hard-coded): "show" would do nothing.
  it("the input turns into text and the eye says it is pressed", () => {
    expect(markup()).toMatch(/<input[^>]*type="text"/);
    expect(markup()).not.toMatch(/<input[^>]*type="password"/);
    expect(markup()).toContain('aria-pressed="true"');
  });

  // Red when: the label starts to change with the state (screen readers would read "Ẩn mật khẩu, pressed").
  it("the eye keeps one name in both states, and swaps its icon", () => {
    expect(markup()).toContain('aria-label="Hiện mật khẩu"');
    expect(markup()).toContain("lucide-eye-off");
  });
});
