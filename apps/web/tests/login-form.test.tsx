// @vitest-environment jsdom
// The sign-in form follows only the pages /api/auth/login may name (review 266042d #3).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const go = vi.fn();
vi.mock("@/lib/navigate", () => ({ go: (path: string) => go(path) }));

const { LoginForm } = await import("@/components/auth/login-form");

afterEach(cleanup);

async function signIn(next: string) {
  vi.stubGlobal("fetch", vi.fn(async () => Response.json({ next })));
  render(<LoginForm />);
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@example.com" } });
  fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "password-marker" } });
  fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
}

describe("LoginForm next", () => {
  it.each(["/", "/check-email"])("goes to %s", async (next) => {
    go.mockReset();
    await signIn(next);
    await waitFor(() => expect(go).toHaveBeenCalledWith(next));
  });

  // Red when: the form follows whatever `next` the response carries (an open redirect).
  it("turns //evil.example into /", async () => {
    go.mockReset();
    await signIn("//evil.example");
    await waitFor(() => expect(go).toHaveBeenCalledWith("/"));
  });

  // Review T2.15 🟡7b. Red when: signing in leaves the drafts of whoever used this device before
  // (a sign-out from another tab or an expired session never reached them).
  it("drops the answers a previous person left on this device", async () => {
    go.mockReset();
    window.localStorage.setItem("essity:draft:old", "{}");
    await signIn("/");
    await waitFor(() => expect(go).toHaveBeenCalled());
    expect(window.localStorage.getItem("essity:draft:old")).toBeNull();
  });
});
