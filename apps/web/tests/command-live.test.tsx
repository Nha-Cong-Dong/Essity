// @vitest-environment jsdom
// T9.3 (US-18 AC1, AC4, AC8): the host in the subject layout draws the bar into the shell's slot.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }), usePathname: () => "/subjects/x/syllabus" }));

import { CommandLive } from "@/components/command-live";

const ID = "31111111-2222-4333-8444-555555555555";
const applied = {
  status: "applied",
  affected: 3,
  op_kinds: ["section_exclude"],
  diff: [{ kind: "doc_section", id: "i", verb: "changed", before: null, after: null }],
};

beforeEach(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query }));
  refresh.mockClear();
  document.body.innerHTML = "";
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function mount(withSlot = true) {
  if (withSlot) document.body.insertAdjacentHTML("beforeend", "<div data-command-slot></div>");
  render(<CommandLive subjectId={ID} />, { container: document.body.appendChild(document.createElement("div")) });
}

describe("CommandLive", () => {
  it("US-18 AC1: a screen with a slot gets the bar", async () => {
    mount();
    expect(await screen.findByLabelText("Gõ một lệnh để sửa")).toBeTruthy();
    expect(document.querySelector("[data-command-slot] form[data-command-bar]")).not.toBeNull();
  });

  it("US-18 AC1: a screen without a slot (the focus shell) gets none", async () => {
    mount(false);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(document.querySelector("form[data-command-bar]")).toBeNull();
  });

  // Red when: the diff is not shown, Hoàn tác does not call undo, or the screen is not read again.
  it("US-18 AC4: a command shows its diff, Hoàn tác undoes it, and each refreshes the screen", async () => {
    mount();
    const fetchFn = vi.fn(async (url: string) => Response.json(url.endsWith("/undo") ? { status: "undone" } : applied));
    vi.stubGlobal("fetch", fetchFn);
    const input = await screen.findByLabelText("Gõ một lệnh để sửa");
    fireEvent.change(input, { target: { value: "bỏ chương 7" } });
    fireEvent.submit(input.closest("form")!);
    await screen.findByText(/Đã làm:/);
    expect(screen.getByText("bỏ 3 mục khỏi đề cương thi")).toBeTruthy();
    expect(refresh).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Hoàn tác" }));
    await screen.findByText(/Đã hoàn tác:/);
    expect(refresh).toHaveBeenCalledTimes(2);
    expect(fetchFn.mock.calls.map((c) => c[0])).toEqual([
      "/api/commands",
      expect.stringMatching(/^\/api\/commands\/[0-9a-f-]{36}\/undo$/),
    ]);
  });

  it("US-18 AC8: when the AI budget is spent the field is off and says so, neutrally", async () => {
    mount();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ error: "quota_hard_cap" }, { status: 429 })),
    );
    const input = await screen.findByLabelText("Gõ một lệnh để sửa");
    fireEvent.change(input, { target: { value: "bỏ chương 7" } });
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(screen.getByText(/tạm tắt vì hết lượt AI/)).toBeTruthy());
    expect(input.getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByRole("button", { name: "Gửi" }).hasAttribute("disabled")).toBe(true);
  });
});
