// @vitest-environment jsdom
// The sign-up form follows only the page /api/auth/register names (review plan R3, review final
// 🟢 on register-form.tsx), as the sign-in form does.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const go = vi.fn();
vi.mock("@/lib/navigate", () => ({ go: (path: string) => go(path) }));

const { RegisterForm } = await import("@/components/auth/register-form");

afterEach(cleanup);
beforeEach(() => go.mockReset());

async function signUp(reply: Response) {
  vi.stubGlobal("fetch", vi.fn(async () => reply));
  render(<RegisterForm />);
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@example.com" } });
  fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "password-marker-123" } });
  fireEvent.click(screen.getByRole("button", { name: "Đăng ký" }));
}

describe("RegisterForm next", () => {
  it("goes to /check-email", async () => {
    await signUp(Response.json({ next: "/check-email" }));
    await waitFor(() => expect(go).toHaveBeenCalledWith("/check-email"));
  });

  // Red when: the form follows whatever `next` the response carries (an open redirect).
  it("turns //evil.example into /check-email", async () => {
    await signUp(Response.json({ next: "//evil.example" }));
    await waitFor(() => expect(go).toHaveBeenCalledWith("/check-email"));
  });

  // Red when: an answer without `next` sends the browser to "/undefined".
  it("an answer without next still goes to /check-email", async () => {
    await signUp(Response.json({}));
    await waitFor(() => expect(go).toHaveBeenCalledWith("/check-email"));
  });
});
