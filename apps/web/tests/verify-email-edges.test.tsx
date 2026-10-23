// @vitest-environment jsdom
// Tester T1.22: edges of the verify-email page that the Coder's tests leave open.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const go = vi.fn();
vi.mock("@/lib/navigate", () => ({ go: (path: string) => go(path) }));
vi.mock("@/lib/link-token", () => ({
  consumeLinkToken: () => "link-token-marker",
  postOnce: (_token: string, post: () => Promise<unknown>) => post(),
}));

const { VerifyEmail } = await import("@/components/auth/verify-email");

async function renderWith(...answers: Response[]) {
  const fetchMock = vi.fn();
  for (const a of answers) fetchMock.mockResolvedValueOnce(a);
  vi.stubGlobal("fetch", fetchMock);
  render(<VerifyEmail />);
  await act(() => vi.advanceTimersByTimeAsync(0));
}

beforeEach(() => {
  go.mockReset();
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("VerifyEmail, T1.22 edges", () => {
  // Red when: the timer or the button trusts `next` without `signedIn` (a session not proven to
  // own the link would be sent into the app).
  it("AC11: signedIn false with a next in the body still shows only 'Đăng nhập' and stays", async () => {
    await renderWith(Response.json({ verified: true, signedIn: false, next: "/today" }));

    expect(screen.getByRole("button", { name: "Đăng nhập" }).getAttribute("href")).toBe("/login");
    expect(screen.queryByRole("button", { name: "Vào hôm nay" })).toBeNull();
    await act(() => vi.advanceTimersByTimeAsync(3000));
    expect(go).not.toHaveBeenCalled();
  });

  // Red when: the timer is started on the failed view, or not started again after "Thử lại".
  it("AC11: a failed check does not go on; 'Thử lại' that verifies then goes once", async () => {
    await renderWith(
      Response.json({ error: "x" }, { status: 503 }),
      Response.json({ verified: true, signedIn: true, next: "/subjects/new" }),
    );
    await act(() => vi.advanceTimersByTimeAsync(3000));
    expect(go).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Thử lại" }));
    });
    await act(() => vi.advanceTimersByTimeAsync(1500));

    expect(go).toHaveBeenCalledExactlyOnceWith("/subjects/new");
  });

  // Red when: an expired link goes on by itself, or the new-link button points at the wrong page.
  it.each([
    [true, "/check-email"],
    [false, "/login"],
  ])("AC11: expired link, signedIn %s: no timer, 'Gửi link mới' → %s", async (signedIn, href) => {
    await renderWith(Response.json({ error: "invalid_or_expired_token", signedIn }, { status: 400 }));

    expect(screen.getByRole("button", { name: "Gửi link mới" }).getAttribute("href")).toBe(href);
    await act(() => vi.advanceTimersByTimeAsync(3000));
    expect(go).not.toHaveBeenCalled();
  });
});
