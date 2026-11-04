// @vitest-environment jsdom
// T2.3c (risk register R46, plan G5): the main nav brings the current item into view when it has to
// scroll (at 280px), without scrolling the page; the layout itself is measured by e2e/layout.spec.ts.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MainNav } from "@/components/main-nav";

afterEach(() => {
  cleanup();
  // jsdom has no scrollIntoView: each test puts back what it adds.
  delete (Element.prototype as Partial<Element>).scrollIntoView;
});

describe("MainNav (T2.3c, R46)", () => {
  // Red when: the effect goes, scrolls the wrong item, or uses block "start" (which scrolls the page).
  it("scrolls the current item into view once, nearest on both axes", () => {
    const scrolled = vi.fn();
    Element.prototype.scrollIntoView = scrolled;
    render(<MainNav current="/subjects" />);
    expect(scrolled).toHaveBeenCalledTimes(1);
    expect(scrolled).toHaveBeenCalledWith({ inline: "nearest", block: "nearest" });
    expect(scrolled.mock.contexts[0]).toBe(screen.getByRole("link", { name: "Môn học" }));
  });

  it("with no current item it scrolls nothing", () => {
    const scrolled = vi.fn();
    Element.prototype.scrollIntoView = scrolled;
    render(<MainNav />);
    expect(scrolled).not.toHaveBeenCalled();
  });

  // Red when: the call is not guarded: a browser (or jsdom) without scrollIntoView would throw.
  it("renders where scrollIntoView does not exist", () => {
    expect(() => render(<MainNav current="/today" />)).not.toThrow();
    expect(screen.getByRole("link", { name: "Hôm nay" }).getAttribute("aria-current")).toBe("page");
  });

  // Red when: the ring is drawn outside the pill, where the scrolling nav clips it (review C2 #1).
  it("draws the focus ring inside each pill", () => {
    render(<MainNav current="/today" />);
    for (const link of screen.getAllByRole("link")) expect(link.className).toMatch(/focus-visible:-outline-offset-2/);
  });

  // V21: five items, graph included, each with a decorative icon.
  it("lists the five items; icons are hidden from assistive tech", () => {
    const { container } = render(<MainNav current="/graph" />);
    expect(screen.getAllByRole("link").map((l) => l.getAttribute("href"))).toEqual([
      "/today", "/subjects", "/kho-kien-thuc", "/graph", "/stats",
    ]);
    expect(container.querySelectorAll('a svg[aria-hidden="true"]')).toHaveLength(5);
    expect(screen.getByRole("link", { name: "Đồ thị" }).getAttribute("aria-current")).toBe("page");
  });

  // Red when: the current item loses its state (colour alone is not enough: aria-current + weight).
  it("marks the current item by weight and colour, with a dot on the bar and a pill on the rail", () => {
    render(<MainNav current="/subjects" />);
    const current = screen.getByRole("link", { name: "Môn học" });
    expect(current.className).toMatch(/aria-\[current=page\]:font-semibold/);
    expect(current.className).toMatch(/aria-\[current=page\]:text-hong/);
    expect(current.className).toMatch(/min-\[1024px\]:aria-\[current=page\]:bg-sunken/);
    expect(current.querySelector('span[aria-hidden="true"]')).not.toBeNull();
  });

  it("keeps the nav landmark that shrinks and scrolls (review of 96bebab)", () => {
    render(<MainNav current="/today" />);
    const nav = screen.getByRole("navigation", { name: "Chính" });
    expect(nav.className).toMatch(/min-w-0/);
    expect(nav.className).toMatch(/overflow-x-auto/);
    expect(nav.className).toMatch(/fixed/);
  });
});
