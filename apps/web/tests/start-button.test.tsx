// @vitest-environment jsdom
// T2.14 (review #21): "Bắt đầu" / "Ôn thêm" POST web's /api/review-sessions, then go to the
// session; signed out goes to /login, nothing left today back to /today, a failure says so.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const go = vi.fn();
vi.mock("@/lib/navigate", () => ({ go: (path: string) => go(path) }));

const { StartButton } = await import("@/components/today/start-button");
const ID = "6b1c2d3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e";

function answer(response: Response | Error) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      if (response instanceof Error) throw response;
      return response;
    }),
  );
}

async function press() {
  render(<StartButton variant="primary-inverse">Bắt đầu</StartButton>);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Bắt đầu" })));
}

describe("StartButton (T2.14)", () => {
  beforeEach(() => go.mockReset());
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  // Red when: the button does not POST, or goes somewhere other than the session it got.
  it("goes to the session web's route answers", async () => {
    answer(Response.json({ id: ID }));
    await press();
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/review-sessions");
    expect(init?.method).toBe("POST");
    expect(go).toHaveBeenCalledWith(`/review/${ID}`);
  });

  it("signed out goes to /login", async () => {
    answer(Response.json({ error: "signed_out" }, { status: 401 }));
    await press();
    expect(go).toHaveBeenCalledWith("/login");
  });

  it("nothing left to review goes back to /today", async () => {
    answer(Response.json({ error: "nothing_to_review" }, { status: 409 }));
    await press();
    expect(go).toHaveBeenCalledWith("/today");
  });

  // Red when: a failed start leaves the button pending with nothing said.
  it("a network failure says so and lets the user press again", async () => {
    answer(new TypeError("fetch failed"));
    await press();
    expect(go).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toBe("Chưa mở được phiên. Thử lại sau giây lát.");
    expect(screen.getByRole("button", { name: "Bắt đầu" }).getAttribute("aria-disabled")).not.toBe("true");
  });
});
