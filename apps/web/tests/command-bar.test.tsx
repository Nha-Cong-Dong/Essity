// @vitest-environment jsdom
// T9.3a (US-18 AC1, AC3, AC4, AC5, AC8; DESIGN §6.14): the command bar and its tray from fixtures.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CommandBar, type CommandBarProps, TIMEOUT_MS } from "@/components/command-bar";
import type { Command, Outcome } from "@/components/command/types";
import {
  COMMAND_STATE_IDS,
  type CommandState,
  EXAMPLE,
  fakeRun,
  fakeUndo,
  initialFor,
  LONG,
  PAGES,
  PRACTICE_EXHAUSTED,
} from "@/lib/fixtures/command-bar";

afterEach(cleanup);
beforeEach(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query }));
});

const touch = () =>
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("coarse"), media: query }));

// JS \b is ASCII-only, so the edges are Unicode lookarounds (DESIGN §4; same as the other screens).
const FORBIDDEN = /(?<!\p{L})(streak|chuỗi|xếp hạng|ranking|trễ|kém|lười|bỏ lỡ|thất bại|phải|cần|kịp)(?!\p{L})/iu;
const PRIMARY = "[data-variant='primary']";

const appCopy = (container: HTMLElement) => {
  const clone = container.cloneNode(true) as HTMLElement;
  clone.querySelectorAll("[data-user]").forEach((el) => el.remove());
  return clone.textContent ?? "";
};

function bar(props: Partial<CommandBarProps> = {}) {
  const run = vi.fn<CommandBarProps["run"]>(async (c) => fakeRun(c.text));
  const undo = vi.fn<CommandBarProps["undo"]>(async () => fakeUndo());
  const all = { example: EXAMPLE, run, undo, ...props };
  const view = render(<CommandBar {...all} />);
  return { run, undo, ...view };
}

const field = () => screen.getByLabelText("Gõ một lệnh để sửa") as HTMLInputElement;
const type = (text: string) => fireEvent.change(field(), { target: { value: text } });
const send = async () => {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
  });
};
const click = async (name: string) => {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name }));
  });
};
const describedBy = (el: HTMLElement) => document.getElementById(el.getAttribute("aria-describedby") ?? "");

describe("banned words", () => {
  it.each(["đã trễ", "Chuỗi ngày", "bạn kém", "bạn phải", "cần làm"])("%s is caught", (text) => {
    expect(text).toMatch(FORBIDDEN);
  });
  it("does not fire inside a longer word", () => {
    expect("trễnải").not.toMatch(FORBIDDEN);
  });
});

describe("every state", () => {
  // US-18 (DESIGN §6.14). Red when: the bar adds a primary, writes a banned word, or has two live regions.
  it.each(COMMAND_STATE_IDS)("%s: no primary, no banned word, one live region, a placeholder from the example", (state) => {
    const { container } = bar({ initial: initialFor(state), example: EXAMPLE });
    expect(container.querySelectorAll(PRIMARY).length).toBe(0);
    expect(appCopy(container)).not.toMatch(FORBIDDEN);
    expect(container.querySelectorAll("[role=status]").length).toBe(1);
    expect(field().placeholder).toBe(`Thử: ${EXAMPLE}`);
    expect(container.querySelectorAll("button, a").length).toBeLessThanOrEqual(4);
  });
});

describe("a command", () => {
  // US-18 AC1. Red when: Gửi does not send, or the field keeps the text of an applied command.
  it("AC1: Gửi sends the command with an id; done shows the change and clears the field", async () => {
    const { run } = bar();
    type("  mục 3.4 kết thúc ở trang 80 ");
    await send();
    expect(run).toHaveBeenCalledOnce();
    expect(run.mock.calls[0][0].text).toBe("mục 3.4 kết thúc ở trang 80");
    expect(run.mock.calls[0][0].id).toMatch(/^[0-9a-f-]{36}$/);
    expect(screen.getByText(/Đã làm:/)).toBeTruthy();
    expect(field().value).toBe("");
    expect(screen.getByRole("button", { name: "Hoàn tác" })).toBeTruthy();
  });

  it("AC1: Enter in the field sends (the form submits)", async () => {
    const { run } = bar();
    type("sửa mục 3.4");
    await act(async () => {
      fireEvent.submit(screen.getByRole("form", { name: "Thanh lệnh" }));
    });
    expect(run).toHaveBeenCalledOnce();
  });

  // Red when: an empty field reaches the API.
  it("an empty field sends nothing and puts focus back on the field", async () => {
    const { run } = bar();
    type("   ");
    await send();
    expect(run).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(field());
  });

  // Red when: an IME's confirming Enter sends a half-typed command.
  it("Enter during IME composition does not submit", () => {
    bar();
    type("sửa");
    const press = (init: KeyboardEventInit) => {
      const event = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true, ...init });
      field().dispatchEvent(event);
      return event.defaultPrevented;
    };
    expect(press({ isComposing: true })).toBe(true);
    expect(press({})).toBe(false);
  });

  // Red when: two quick presses apply the command twice.
  it("a second submit while the first is running sends nothing", async () => {
    let finish: (o: Outcome) => void = () => {};
    const run = vi.fn(() => new Promise<Outcome>((resolve) => (finish = resolve)));
    bar({ run });
    type("sửa mục 3.4");
    await send();
    expect(field().readOnly).toBe(true);
    expect(screen.getByText("Đang hiểu lệnh…")).toBeTruthy();
    fireEvent.submit(screen.getByRole("form", { name: "Thanh lệnh" }));
    expect(run).toHaveBeenCalledOnce();
    await act(async () => finish({ kind: "done", diff: PAGES }));
  });

  // US-18 AC8 (the limit is MAX_COMMAND_CHARS of T9.1). Red when: a long command is sent.
  it("a command over the limit is not sent and says so; NFD text is counted as NFC", async () => {
    const { run } = bar();
    type("a".repeat(501));
    await send();
    expect(run).not.toHaveBeenCalled();
    expect(screen.getByText("Lệnh dài quá. Rút gọn còn tối đa 500 ký tự.")).toBeTruthy();
    expect(field().value.length).toBe(501);
    type("ế".normalize("NFD").repeat(500));
    await send();
    expect(run).toHaveBeenCalledOnce();
    expect(run.mock.calls[0][0].text).toBe("ế".repeat(500));
  });

  // US-18 AC3. Red when: an unclear command clears the field or is "guessed".
  it("AC3: unclear shows 'Chưa rõ: …' and keeps the words", async () => {
    bar();
    type("sửa nó?");
    await send();
    expect(screen.getByText(/^Chưa rõ:/)).toBeTruthy();
    expect(field().value).toBe("sửa nó?");
  });

  it("a command outside the list says it is not done by command", async () => {
    bar();
    type("xóa môn này");
    await send();
    expect(screen.getByText("Thao tác này không làm bằng lệnh.")).toBeTruthy();
  });

  // US-18 AC4. Red when: 11 or more items show no number.
  it("AC4: many items: the number is in the tray", () => {
    bar({ initial: initialFor("many") });
    expect(screen.getByText(/14/)).toBeTruthy();
  });
});

describe("errors", () => {
  const failing = (certain: boolean) => vi.fn<CommandBarProps["run"]>(async () => ({ kind: "error", certain }));

  // Red when: a retry sends a new id (core would apply the command twice).
  it("Thử lại and Gửi with the same words reuse the command id; changed words get a new one", async () => {
    const run = failing(false);
    bar({ run });
    type("sửa mục 3.4");
    await send();
    expect(screen.getByText(/Chưa chắc lệnh đã chạy/)).toBeTruthy();
    await click("Thử lại");
    await send();
    type("sửa mục 3.5");
    await send();
    const ids = run.mock.calls.map((c) => (c[0] as Command).id);
    expect(ids[1]).toBe(ids[0]);
    expect(ids[2]).toBe(ids[0]);
    expect(ids[3]).not.toBe(ids[0]);
  });

  it("a sure failure says nothing changed; Thử lại is described by the reason", async () => {
    bar({ run: failing(true) });
    type("sửa mục 3.4");
    await send();
    expect(screen.getByText("Không chạy được lệnh. Chưa có gì thay đổi.")).toBeTruthy();
    expect(describedBy(screen.getByRole("button", { name: "Thử lại" }))?.textContent).toContain("Chưa có gì");
    expect(field().value).toBe("sửa mục 3.4");
  });

  // Red when: a hung request keeps "Đang hiểu lệnh…" forever.
  it("after 20 seconds the unsure variant appears", async () => {
    vi.useFakeTimers();
    try {
      bar({ run: () => new Promise<Outcome>(() => {}) });
      type("sửa mục 3.4");
      await send();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(TIMEOUT_MS + 1);
      });
      expect(screen.getByText(/Chưa chắc lệnh đã chạy/)).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("the latest-command rule", () => {
  // Red when: after a failed or refused command the one that can still be undone has no button.
  const WITH_LATEST: CommandState[] = ["unclear", "too-long", "error-unsure", "pending-ai"];
  it.each(WITH_LATEST)("%s: names the latest command beside Hoàn tác, described by that line", (state) => {
    bar({ initial: initialFor(state) });
    expect(screen.getByText(/Lệnh gần nhất:/)).toBeTruthy();
    expect(describedBy(screen.getByRole("button", { name: "Hoàn tác" }))?.textContent).toContain("Lệnh gần nhất:");
  });

  it("not-allowed names it too when something can be undone", () => {
    bar({ initial: { ...initialFor("not-allowed"), stack: [PAGES] } });
    expect(screen.getByText(/Lệnh gần nhất:/)).toBeTruthy();
  });

  // Critic r3 P1. Red when: a refused undo offers the same Hoàn tác again, or Hoàn tác can run
  // while a new command is still being understood.
  it("undo-failed and understanding show no Hoàn tác and no latest line", () => {
    for (const state of ["undo-failed", "understanding"] as const) {
      bar({ initial: { ...initialFor(state), stack: [PAGES] } });
      expect(screen.queryByRole("button", { name: "Hoàn tác" })).toBeNull();
      expect(screen.queryByText(/Lệnh gần nhất:/)).toBeNull();
      cleanup();
    }
  });

  // Critic r3 P2, US-18 AC4. Red when: the undone line drops the count of a large command.
  it("an undone command of 14 items still says 14", () => {
    bar({ initial: { tray: { kind: "undone", diff: initialFor("many").stack[0] }, stack: [], text: "" } });
    expect(screen.getByText(/Đã hoàn tác:/).closest("p")?.textContent).toContain("14");
  });

  it("no line and no button when nothing can be undone", () => {
    bar({ initial: initialFor("not-allowed") });
    expect(screen.queryByText(/Lệnh gần nhất:/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Hoàn tác" })).toBeNull();
  });
});

describe("undo", () => {
  // US-18 AC5. Red when: undo is not one tap, or does not step back newest first.
  it("AC5: Hoàn tác is one tap; the previous command is shown and can be undone next", async () => {
    const { undo } = bar({ initial: initialFor("undone-previous") });
    expect(screen.getByText(/Đã hoàn tác:/)).toBeTruthy();
    expect(screen.getByText(/Lệnh trước đó:/)).toBeTruthy();
    await click("Hoàn tác lệnh trước");
    expect(undo).toHaveBeenCalledOnce();
    expect(screen.getByText(/Đã hoàn tác:/).closest("p")?.textContent).toContain("trang kết thúc");
    expect(screen.queryByRole("button", { name: "Hoàn tác lệnh trước" })).toBeNull();
  });

  it("AC5: a refused undo says why; a known object gets a link built from kind and id", async () => {
    const id = "0b8f1d2e-0000-4000-8000-0000000000c1";
    const undo = vi.fn(async () => ({ kind: "undo-failed" as const, reason: "thẻ đã đổi", ref: { kind: "card", id } }));
    bar({ initial: initialFor("done"), undo });
    await click("Hoàn tác");
    expect(screen.getByText(/Không hoàn tác được:/).textContent).toContain("thẻ đã đổi");
    expect(screen.getByRole("link", { name: "Xem thẻ" }).getAttribute("href")).toBe(`/cards/${id}`);
  });

  // Red when: an unknown kind or a crafted id produces a link.
  it("an unknown kind gives no link", () => {
    const tray = { kind: "undo-failed" as const, reason: "x", ref: { kind: "javascript:alert(1)", id: "a" } };
    bar({ initial: { tray, stack: [], text: "" } });
    expect(screen.queryByRole("link")).toBeNull();
  });
});

describe("quota (US-18 AC8)", () => {
  // Red when: the field loses the typed words, can be edited, or the sentence is missing.
  it("pending_ai: the field keeps its words read-only and aria-disabled, Gửi is disabled, one calm sentence", () => {
    bar({ initial: initialFor("pending-ai") });
    expect(field().readOnly).toBe(true);
    expect(field().getAttribute("aria-disabled")).toBe("true");
    expect(field().value).toBe("mục 3.5 kết thúc ở trang 92");
    expect((screen.getByRole("button", { name: "Gửi" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Thanh lệnh tạm tắt vì hết lượt AI. Bạn vẫn sửa trực tiếp được.")).toBeTruthy();
    expect(describedBy(field())?.textContent).toContain("hết lượt AI");
  });

  it("the Luyện tập screen passes a longer sentence", () => {
    bar({ initial: initialFor("pending-ai-practice"), exhaustedNote: PRACTICE_EXHAUSTED });
    expect(screen.getByText(/trừ đổi dạng câu và gắn lại câu/)).toBeTruthy();
  });

  it("entering pending_ai moves focus to the field for a pointer and to the tray on touch", async () => {
    const run = async (): Promise<Outcome> => ({ kind: "pending-ai" });
    bar({ run });
    type("sửa mục 3.4");
    await send();
    expect(document.activeElement).toBe(field());
    cleanup();
    touch();
    bar({ run });
    type("sửa mục 3.4");
    await send();
    expect(document.activeElement).toBe(document.querySelector("[data-tray]"));
  });
});

describe("focus after a button vanishes", () => {
  // Red when: focus falls to <body> after Hoàn tác or Thử lại.
  it("undo: field for a pointer, tray on touch", async () => {
    bar({ initial: initialFor("done") });
    await click("Hoàn tác");
    expect(document.activeElement).toBe(field());
    cleanup();
    touch();
    bar({ initial: initialFor("done") });
    await click("Hoàn tác");
    expect(document.activeElement).toBe(document.querySelector("[data-tray]"));
  });

  it("an error moves focus to Thử lại for a pointer", async () => {
    bar({ run: async () => ({ kind: "error", certain: true }) });
    type("sửa mục 3.4");
    await send();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Thử lại" }));
  });
});

describe("long text", () => {
  it("a very long name and values stay in the diff; the name is cut", () => {
    const { container } = bar({ initial: initialFor("long") });
    expect(container.querySelector("[data-diff]")?.textContent).toContain(LONG.to?.slice(0, 20));
    expect(screen.getByText(/Đã làm:/).closest("p")?.textContent).toContain("…");
  });
});
