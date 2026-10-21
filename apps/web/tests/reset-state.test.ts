import { describe, expect, it } from "vitest";

import { afterReset } from "@/lib/reset-state";

const TOKEN = "t";

describe("afterReset: the screen after 'Lưu mật khẩu' (F6, review 7ea491c #2)", () => {
  it("done after 200", () => {
    expect(afterReset(TOKEN, { status: 200, data: { done: true } })).toEqual({ view: "done" });
  });

  it.each(["too_short", "common", "invalid_password"])(
    "a refused password (%s) keeps the form and the token, so the link still works",
    (error) => {
      expect(afterReset(TOKEN, { status: 422, error })).toEqual({ view: "form", token: TOKEN, error });
    },
  );

  it("only an expired or used link shows 'expired'", () => {
    expect(afterReset(TOKEN, { status: 400, error: "invalid_or_expired_token" })).toEqual({
      view: "expired",
    });
  });

  it("a network failure or a 429 keeps the form and the token", () => {
    expect(afterReset(TOKEN, { status: 0, error: "unavailable" })).toMatchObject({ view: "form", token: TOKEN });
    expect(afterReset(TOKEN, { status: 429, error: "rate_limited", retryAfter: 600 })).toEqual({
      view: "form",
      token: TOKEN,
      error: "rate_limited",
      retryAfter: 600,
    });
  });
});
