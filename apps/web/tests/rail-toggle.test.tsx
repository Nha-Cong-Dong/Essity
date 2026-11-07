// @vitest-environment jsdom
// SHELL-ART: the sidebar collapse button (aria-expanded, remembered in localStorage, safe when storage throws).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RAIL_KEY, RailToggle } from "@/components/rail-toggle";

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.rail;
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("RailToggle", () => {
  it("starts open and flips aria-expanded, html[data-rail] and localStorage", () => {
    render(<RailToggle />);
    const btn = screen.getByRole("button", { name: "Thu gọn thanh bên" });
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(btn);
    const open = screen.getByRole("button", { name: "Mở rộng thanh bên" });
    expect(open.getAttribute("aria-expanded")).toBe("false");
    expect(document.documentElement.dataset.rail).toBe("collapsed");
    expect(localStorage.getItem(RAIL_KEY)).toBe("collapsed");
    fireEvent.click(open);
    expect(document.documentElement.dataset.rail).toBe("open");
    expect(localStorage.getItem(RAIL_KEY)).toBe("open");
  });

  it("restores the saved collapsed state on mount", () => {
    localStorage.setItem(RAIL_KEY, "collapsed");
    render(<RailToggle />);
    expect(screen.getByRole("button", { name: "Mở rộng thanh bên" }).getAttribute("aria-expanded")).toBe("false");
    expect(document.documentElement.dataset.rail).toBe("collapsed");
  });

  it("still works when storage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    render(<RailToggle />);
    const btn = screen.getByRole("button", { name: "Thu gọn thanh bên" });
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(btn);
    expect(screen.getByRole("button", { name: "Mở rộng thanh bên" }).getAttribute("aria-expanded")).toBe("false");
  });
});
