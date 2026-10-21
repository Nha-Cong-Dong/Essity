import { describe, expect, it, vi } from "vitest";

import { authMessage, rateLimitMessage, resendWait } from "@/lib/auth-errors";
import { consumeLinkToken, postOnce } from "@/lib/link-token";
import { maskEmail } from "@/lib/mask-email";
import { signOut } from "@/lib/sign-out";

describe("authMessage (DESIGN.md §6.1)", () => {
  it("AC1: each password reason has its own sentence", () => {
    const sentences = ["too_short", "too_long", "common", "same_as_email"].map(authMessage);
    expect(sentences[0]).toBe("Mật khẩu cần ít nhất 8 ký tự. Không cần ký tự đặc biệt.");
    expect(new Set(sentences).size).toBe(4);
    for (const sentence of sentences) expect(sentence).not.toBe(authMessage("unavailable"));
  });

  it("AC1: an unknown reason gets a generic sentence, not the code", () => {
    expect(authMessage("something_new")).toBe(authMessage("unavailable"));
    expect(authMessage(undefined)).toBe(authMessage("unavailable"));
  });
});

describe("rateLimitMessage (AC6, review b26f601)", () => {
  it("says 15 minutes for a sign-in lockout (DESIGN.md §6.1)", () => {
    expect(rateLimitMessage(15 * 60)).toBe("Bạn đã thử quá nhiều lần. Thử lại sau 15 phút.");
    expect(rateLimitMessage(undefined)).toBe("Bạn đã thử quá nhiều lần. Thử lại sau 15 phút.");
  });

  it("follows Retry-After, so a sign-up limit of an hour does not promise 15 minutes", () => {
    expect(rateLimitMessage(3600)).toBe("Bạn đã thử quá nhiều lần. Thử lại sau 60 phút.");
    expect(rateLimitMessage(3600)).not.toContain("15 phút");
  });

  it("rounds up and never says 0 minutes", () => {
    expect(rateLimitMessage(61)).toBe("Bạn đã thử quá nhiều lần. Thử lại sau 2 phút.");
    expect(rateLimitMessage(5)).toBe("Bạn đã thử quá nhiều lần. Thử lại sau 1 phút.");
  });
});

describe("maskEmail (DESIGN.md §6.1 /check-email)", () => {
  it("keeps two letters and the domain", () => {
    expect(maskEmail("minhanh.k21@sv.edu.vn")).toBe("mi•••••@sv.edu.vn");
  });

  it("never shows more of a short name", () => {
    expect(maskEmail("a@x.vn")).toBe("a•••••@x.vn");
    expect(maskEmail("ab@x.vn")).toBe("a•••••@x.vn");
  });
});

describe("resendWait (AC2, F3)", () => {
  it("waits 60 seconds after a resend", () => {
    expect(resendWait({ status: 200, data: {} })).toBe(60);
  });

  it("restarts from Retry-After on 429, not with an error", () => {
    expect(resendWait({ status: 429, error: "rate_limited", retryAfter: 42 })).toBe(42);
    expect(resendWait({ status: 429, error: "rate_limited" })).toBe(60);
  });

  it("lets the user try again at once after a network failure", () => {
    expect(resendWait({ status: 0, error: "unavailable" })).toBe(0);
  });
});

describe("consumeLinkToken (F8, PLAN T1.13 note)", () => {
  function fakeWindow(href: string) {
    const replaced: string[] = [];
    return {
      replaced,
      win: {
        location: { href },
        history: { replaceState: (_state: unknown, _unused: string, url: string) => replaced.push(url) },
      },
    };
  }

  it("takes the token and removes it from the address bar and the history", () => {
    const { win, replaced } = fakeWindow("http://localhost:3000/verify-email?token=abc123");

    expect(consumeLinkToken(win)).toBe("abc123");
    expect(replaced).toEqual(["/verify-email"]);
  });

  it("returns null without a token, and touches nothing", () => {
    const { win, replaced } = fakeWindow("http://localhost:3000/verify-email");

    expect(consumeLinkToken(win)).toBeNull();
    expect(replaced).toEqual([]);
  });
});

describe("postOnce (F8)", () => {
  it("posts a token once even when React runs the effect twice (StrictMode)", async () => {
    const post = vi.fn(async () => "result");

    const [first, second] = await Promise.all([postOnce("t1", post), postOnce("t1", post)]);

    expect(post).toHaveBeenCalledOnce();
    expect(first).toBe("result");
    expect(second).toBe("result");
  });

  it("posts each token on its own", async () => {
    const post = vi.fn(async () => "result");

    await postOnce("t2", post);
    await postOnce("t3", post);

    expect(post).toHaveBeenCalledTimes(2);
  });
});

describe("signOut (review cdbaa25 #1)", () => {
  it("leaves for /login once web has cleared the cookie", async () => {
    const assign = vi.fn();

    const ok = await signOut({ post: async () => ({ status: 200, data: { next: "/login" } }), assign });

    expect(ok).toBe(true);
    expect(assign).toHaveBeenCalledWith("/login");
  });

  it.each([
    ["a refused origin", { status: 403, error: "forbidden_origin" }],
    ["a network failure", { status: 0, error: "unavailable" }],
  ])("stays on the page after %s, so nobody believes they are signed out", async (_name, result) => {
    const assign = vi.fn();

    const ok = await signOut({ post: async () => result, assign });

    expect(ok).toBe(false);
    expect(assign).not.toHaveBeenCalled();
  });

  it("goes where web says (F2: /register after \"Sai email?\")", async () => {
    const assign = vi.fn();

    await signOut({ post: async () => ({ status: 200, data: { next: "/login" } }), assign, then: "/register" });

    expect(assign).toHaveBeenCalledWith("/register");
  });
});
