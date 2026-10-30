// @vitest-environment jsdom
// T9.10a (US-19 AC1-AC4, AC6; DESIGN §6.15): the Đồ thị screen from fixtures. The Cytoscape frame
// is replaced by a stub that reports what it was given: the library needs a real canvas.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GraphScreen } from "@/components/graph/graph-screen";
import { GRAPH_STATE_IDS, type GraphState } from "@/lib/fixtures/graph";
import { COPY } from "@/lib/graph";

const nav = vi.hoisted(() => ({ replace: vi.fn(), query: "" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: nav.replace }),
  usePathname: () => "/design-preview/graph",
  useSearchParams: () => new URLSearchParams(nav.query),
}));
vi.mock("next/dynamic", () => ({
  default: () =>
    function CanvasStub(props: { view: { cards: unknown[]; edges: unknown[] }; onSelectCard: (id: string) => void }) {
      return (
        <div data-canvas-stub data-nodes={props.view.cards.length} data-edges={props.view.edges.length}>
          <button type="button" onClick={() => props.onSelectCard("c1")}>
            tap c1
          </button>
        </div>
      );
    },
}));

afterEach(() => {
  cleanup();
  nav.query = "";
  nav.replace.mockReset();
});

const show = (state: GraphState, query = "") => {
  nav.query = query;
  return render(<GraphScreen state={state} />);
};
// DESIGN §4: no score, no ranking, no nudge to tend the graph (AC6). Only the words the app writes.
const FORBIDDEN =
  /(?<!\p{L})(streak|chuỗi|xếp hạng|điểm|hạng|yếu|chưa học|hãy|chăm sóc|cập nhật đồ thị|liên kết mới|nhắc)(?!\p{L})/iu;
const appCopy = (container: HTMLElement) => {
  const clone = container.cloneNode(true) as HTMLElement;
  clone.querySelectorAll("[data-user]").forEach((el) => el.remove());
  return clone.textContent ?? "";
};

describe("every state", () => {
  // Red when: a state throws, or a normal state grows a primary button.
  it.each(GRAPH_STATE_IDS)("US-19 AC3, AC6: %s renders; only the error state has a primary", (state) => {
    const { container } = show(state);
    expect(container.querySelector("h1")?.textContent).toBe("Đồ thị");
    const primaries = container.querySelectorAll("[data-variant='primary']").length;
    expect(primaries).toBe(state === "error" ? 1 : 0);
  });
  // Red when: the app writes a banned or pressuring word on any state (AC6).
  it.each(GRAPH_STATE_IDS)("US-19 AC6: %s has no banned word", (state) => {
    const { container } = show(state);
    expect(appCopy(container)).not.toMatch(FORBIDDEN);
  });
});

describe("states of DESIGN §6.15", () => {
  it("empty says the DESIGN line and nothing is drawn", () => {
    show("empty");
    expect(screen.getByText(COPY.empty)).toBeTruthy();
    expect(document.querySelector("[data-canvas-stub]")).toBeNull();
  });
  it("error says the DESIGN line with Thử lại, and Thử lại loads the screen", () => {
    show("error");
    expect(screen.getByText(COPY.error)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Thử lại" }));
    expect(screen.queryByText(COPY.error)).toBeNull();
  });
  it("loading is a busy skeleton with a name", () => {
    show("loading");
    expect(document.querySelector("[aria-busy='true']")?.getAttribute("aria-label")).toBe("Đang tải đồ thị");
  });
  // Red when: the over-300 line differs from DESIGN, or the canvas gets more than 300 cards.
  it("US-19 AC3: many cards: the neutral line and at most 300 nodes", () => {
    show("many");
    expect(screen.getByText(COPY.truncated)).toBeTruthy();
    expect(document.querySelector("[data-canvas-stub]")?.getAttribute("data-nodes")).toBe("300");
  });
  // Red when: turning kinds off hides the cards, or the summary lies about the view.
  it("US-19 AC3: filtered by kind: the canvas and the summary follow the filter", () => {
    show("filtered");
    expect(document.querySelector("[data-canvas-stub]")?.getAttribute("data-edges")).toBe("2");
    expect(screen.getByText(/Đồ thị có 5 thẻ và 2 liên kết/)).toBeTruthy();
    expect(screen.getByText(/Loại liên kết \(1\/5\)/)).toBeTruthy();
  });
  it("no link of the chosen kinds: neutral line and Bật lại tất cả", () => {
    show("few", "edge=");
    expect(screen.getByText(COPY.noKind)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Bật lại tất cả" }));
    expect(nav.replace).toHaveBeenCalledWith(expect.stringContaining("edge=prerequisite%2Cpart_of"), { scroll: false });
  });
});

describe("filters and the list switch", () => {
  // Red when: the switch does not say its state, or does not write it to the URL.
  it("US-19 AC3: the switch is role=switch, in front of the frame, and writes ?view=list", () => {
    show("few");
    const sw = screen.getByRole("switch", { name: "Xem dạng danh sách" });
    expect(sw.getAttribute("aria-checked")).toBe("false");
    expect(sw.compareDocumentPosition(document.querySelector("[data-canvas-stub]")!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.click(sw);
    expect(nav.replace).toHaveBeenCalledWith("/design-preview/graph?view=list", { scroll: false });
  });
  it("US-19 AC3: a kind chip is a real checkbox and writes ?edge=", () => {
    show("few");
    fireEvent.click(screen.getByRole("checkbox", { name: /Đối lập hoặc so sánh/ }));
    const url = nav.replace.mock.calls[0]![0] as string;
    expect(decodeURIComponent(url)).toContain("edge=prerequisite,part_of,example_of,applies_to");
  });
  it("US-19 AC3: the section filter keeps the sections in the list", () => {
    show("few");
    const select = screen.getByLabelText("Mục") as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(["", "ch1", "ch1-1", "ch1-2", "ch2", "ch2-1"]);
    expect(select.value).toBe("ch1");
  });
  // Red when: the canvas controls sit inside the aria-hidden frame (a control a reader cannot reach).
  it("US-19 AC3: no control sits inside an aria-hidden region", () => {
    show("few");
    expect(document.querySelector("[aria-hidden='true'] button, [aria-hidden='true'] a")).toBeNull();
  });
});

describe("the list is the canvas in words", () => {
  // Red when: the list and the canvas could show different numbers of cards or links.
  it("US-19 AC3: same cards and links in the list as in the canvas view", () => {
    const { unmount } = show("few");
    const nodes = Number(document.querySelector("[data-canvas-stub]")!.getAttribute("data-nodes"));
    const edges = Number(document.querySelector("[data-canvas-stub]")!.getAttribute("data-edges"));
    unmount();
    show("few", "view=list");
    expect(document.querySelectorAll("[data-edge-row]")).toHaveLength(edges);
    const cardsInList = new Set([...document.querySelectorAll("[data-card]")].map((el) => el.getAttribute("data-card")));
    expect(cardsInList.size).toBe(nodes);
  });
  it("US-19 AC3: only one form of the list is in the DOM (a ul below 768 px)", () => {
    show("few", "view=list");
    expect(document.querySelector("table")).toBeNull();
    expect(document.querySelectorAll("ul[aria-label='Liên kết giữa các thẻ'] > li")).toHaveLength(6);
  });
  it("US-19 AC3: from 768 px it is a real table with column headers", () => {
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("min-width"), addEventListener() {}, removeEventListener() {} }));
    show("few", "view=list");
    const table = document.querySelector("table")!;
    expect([...table.querySelectorAll("th[scope='col']")].map((th) => th.textContent)).toEqual([
      "Thẻ",
      "Loại liên kết",
      "Thẻ kia",
      "Bằng chứng",
    ]);
    expect(table.querySelectorAll("tbody tr")).toHaveLength(6);
    expect(document.querySelector("ul[aria-label='Liên kết giữa các thẻ']")).toBeNull();
  });
  it("US-19 AC3: cards with no visible link are listed apart", () => {
    show("filtered", "view=list");
    const alone = document.querySelector("[data-unlinked]")!;
    expect(within(alone as HTMLElement).getAllByRole("button")).toHaveLength(2);
  });
  it("US-19 AC3: a card button names the card and its link, and has a way past the list", () => {
    show("few", "view=list");
    expect(screen.getAllByRole("button", { name: /^Chọn thẻ Bắt tay ba bước, liên kết Tiên quyết với thẻ Số thứ tự/ }).length).toBe(1);
    expect(screen.getByRole("link", { name: "Bỏ qua danh sách" }).getAttribute("href")).toBe("#after-list");
  });
});

describe("the tray", () => {
  // Red when: choosing a card in the list does not show its text, anchors, and its links' quotes.
  it("US-19 AC4: choosing a card shows the card, its anchor, and each link with its evidence", () => {
    show("few", "view=list");
    fireEvent.click(screen.getAllByRole("button", { name: /^Chọn thẻ Bắt tay ba bước/ })[0]!);
    const tray = document.querySelector("[data-tray]") as HTMLElement;
    expect(within(tray).getByRole("heading", { level: 2 }).textContent).toBe("Bắt tay ba bước");
    expect(tray.textContent).toContain("Kết nối TCP được thiết lập bằng bắt tay ba bước.");
    expect(within(tray).getByText("Tiên quyết")).toBeTruthy();
    expect(tray.textContent).toContain("Sau khi kết nối mở, mỗi byte được đánh số thứ tự.");
    expect(within(tray).getByText("Vì sao TCP cần bắt tay ba bước?")).toBeTruthy();
  });
  it("US-19 AC4: the selected state opens with a card chosen and a live status", () => {
    show("selected");
    const tray = document.querySelector("[data-tray]") as HTMLElement;
    expect(within(tray).getByRole("heading", { level: 2 }).textContent).toBe("Bắt tay ba bước");
    expect(within(tray).getByRole("status").textContent).toBe("Đã chọn: Bắt tay ba bước");
  });
  it("US-19 AC4: a link in the tray moves to the other card; two steps away sits under Xa hơn", () => {
    show("selected");
    const tray = document.querySelector("[data-tray]") as HTMLElement;
    expect(tray.querySelector("details summary")?.textContent).toBe("Xa hơn");
    fireEvent.click(tray.querySelector("[data-link-to='c2']")!);
    expect(within(tray).getByRole("heading", { level: 2 }).textContent).toBe("Số thứ tự và xác nhận");
  });
  it("US-19 AC4: Đóng clears it and the tray says what to do", () => {
    show("selected");
    fireEvent.click(screen.getByRole("button", { name: "Đóng" }));
    expect(screen.getByText("Chọn một thẻ hoặc một đường để xem chi tiết.")).toBeTruthy();
  });
  it("US-19 AC4: tapping a node in the canvas selects its card", () => {
    show("few");
    fireEvent.click(screen.getByRole("button", { name: "tap c1" }));
    expect(within(document.querySelector("[data-tray]") as HTMLElement).getByRole("heading", { level: 2 }).textContent).toBe(
      "Bắt tay ba bước",
    );
  });
  it("long titles are shown whole in the tray and the list (wrap, never cut)", () => {
    show("long", "view=list");
    expect(document.querySelector("[data-tray] h2")?.textContent).toMatch(/Sosánhhaigiaothức.*kỳthicuốikỳ$/);
    expect(document.querySelector("[data-tray] h2")?.className).toContain("wrap-anywhere");
  });
});

describe("AC6: not a place to tend", () => {
  // Red when: the main navigation or any shared shell links to the graph.
  it("US-19 AC6: nothing in the main navigation links to /graph", async () => {
    const { readFileSync } = await import("node:fs");
    const path = await import("node:path");
    const dir = path.resolve(import.meta.dirname, "..", "components");
    for (const f of ["main-nav.tsx", "shells.tsx", "account-menu.tsx"]) {
      expect(readFileSync(path.join(dir, f), "utf-8")).not.toMatch(/graph/i);
    }
  });
  it("US-19 AC6: no badge or counter of new links on the screen", () => {
    const { container } = show("few");
    expect(container.querySelector("[data-slot='badge']")).toBeNull();
    expect(appCopy(container)).not.toMatch(/\bmới\b/i);
  });
});
