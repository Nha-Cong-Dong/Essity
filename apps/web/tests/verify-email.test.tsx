// @vitest-environment jsdom
// After verifying, the page names where it goes and goes there by itself (T1.22, us-12 AC11,
// decision A; plan E5). jsdom cannot follow a navigation, so `go` is replaced.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const go = vi.fn();
vi.mock("@/lib/navigate", () => ({ go: (path: string) => go(path) }));
vi.mock("@/lib/link-token", () => ({
  consumeLinkToken: () => "link-token-marker",
  postOnce: (_token: string, post: () => Promise<unknown>) => post(),
}));

const { VerifyEmail } = await import("@/components/auth/verify-email");

function answer(body: object) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json(body)),
  );
}

/** Renders and lets the POST settle; the timers stay frozen. */
async function verified(body: object) {
  answer(body);
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

describe("VerifyEmail after the link is verified", () => {
  // Review T2.15 🟡4. Red when: the sign-in this link makes leaves the last person's drafts.
  it("drops the answers kept on this device when it signs in", async () => {
    window.localStorage.setItem("essity:draft:old", "{}");
    await verified({ verified: true, signedIn: true, next: "/today" });
    expect(window.localStorage.getItem("essity:draft:old")).toBeNull();
  });

  // Red when: the button keeps the old baseline label, or its label and its page disagree.
  it.each([
    ["/subjects/new", "Tạo môn đầu tiên"],
    ["/today", "Vào hôm nay"],
  ])("AC11: next %s shows '%s', linking there", async (next, label) => {
    await verified({ verified: true, signedIn: true, next });

    const button = screen.getByRole("button", { name: label });
    expect(button.getAttribute("href")).toBe(next);
    expect(screen.queryByText(/điểm xuất phát/i)).toBeNull();
  });

  // Red when: the wait changes, or the page goes somewhere other than the button says.
  it("AC11: goes to the page at 1500 ms, not at 1499", async () => {
    await verified({ verified: true, signedIn: true, next: "/subjects/new" });

    await act(() => vi.advanceTimersByTimeAsync(1499));
    expect(go).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(1));
    expect(go).toHaveBeenCalledExactlyOnceWith("/subjects/new");
  });

  // Red when: `next` is followed without safeNext (an open redirect, or a page that is gone).
  it.each([undefined, "//evil.example", "/onboarding"])("AC11: next %s falls back to /today", async (next) => {
    await verified({ verified: true, signedIn: true, next });

    expect(screen.getByRole("button", { name: "Vào hôm nay" }).getAttribute("href")).toBe("/today");
    await act(() => vi.advanceTimersByTimeAsync(1500));
    expect(go).toHaveBeenCalledExactlyOnceWith("/today");
  });

  // Red when: the button lets the anchor navigate while the timer still runs (two loads).
  it("AC11: a click at 500 ms goes once, the timer does not go again", async () => {
    await verified({ verified: true, signedIn: true, next: "/today" });

    await act(() => vi.advanceTimersByTimeAsync(500));
    // fireEvent answers false when the anchor's own navigation was prevented.
    expect(fireEvent.click(screen.getByRole("button", { name: "Vào hôm nay" }))).toBe(false);
    await act(() => vi.advanceTimersByTimeAsync(1500));
    expect(go).toHaveBeenCalledExactlyOnceWith("/today");
  });

  // Red when: a Ctrl/Cmd/Shift click (a new tab) is turned into a load of this tab, or stops this
  // tab from going on while it still says "Đang chuyển tiếp…" (review 418b592).
  it.each([{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }])(
    "AC11: a click with %o is left to the browser; this tab still goes on",
    async (modifier) => {
      await verified({ verified: true, signedIn: true, next: "/today" });

      expect(fireEvent.click(screen.getByRole("button", { name: "Vào hôm nay" }), modifier)).toBe(true);
      expect(go).not.toHaveBeenCalled();
      await act(() => vi.advanceTimersByTimeAsync(1500));
      expect(go).toHaveBeenCalledExactlyOnceWith("/today");
    },
  );

  it("AC11: leaving the page cancels the timer", async () => {
    await verified({ verified: true, signedIn: true, next: "/today" });

    cleanup();
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(go).not.toHaveBeenCalled();
  });

  // Red when: someone not proven to own the link is sent on into the app.
  it("AC11: not signed in shows 'Đăng nhập' and does not go on", async () => {
    await verified({ verified: true, signedIn: false });

    expect(screen.getByRole("button", { name: "Đăng nhập" }).getAttribute("href")).toBe("/login");
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(go).not.toHaveBeenCalled();
  });

  describe("reduced motion", () => {
    function prefers(reduce: boolean) {
      vi.stubGlobal(
        "matchMedia",
        vi.fn((query: string) => ({ matches: reduce && query.includes("reduce"), media: query })),
      );
    }

    // Red when: the page moves on by itself for someone who asked for less motion.
    it("AC11: reduce keeps the button and does not go on", async () => {
      prefers(true);
      await verified({ verified: true, signedIn: true, next: "/subjects/new" });

      expect(screen.getByRole("button", { name: "Tạo môn đầu tiên" }).getAttribute("href")).toBe("/subjects/new");
      // Red when: the page says it is moving on while it stays (review 9d51d23 #3).
      expect(screen.queryByText("Đang chuyển tiếp…")).toBeNull();
      await act(() => vi.advanceTimersByTimeAsync(2000));
      expect(go).not.toHaveBeenCalled();
    });

    it("AC11: no-preference goes on", async () => {
      prefers(false);
      await verified({ verified: true, signedIn: true, next: "/today" });
      expect(screen.getByText("Đang chuyển tiếp…")).toBeTruthy();

      await act(() => vi.advanceTimersByTimeAsync(1500));
      expect(go).toHaveBeenCalledExactlyOnceWith("/today");
    });

    // Red when: matchMedia is called where it does not exist (jsdom, old browsers) and throws.
    it("AC11: without matchMedia it goes on", async () => {
      vi.stubGlobal("matchMedia", undefined);
      await verified({ verified: true, signedIn: true, next: "/today" });

      await act(() => vi.advanceTimersByTimeAsync(1500));
      expect(go).toHaveBeenCalledExactlyOnceWith("/today");
    });
  });
});
