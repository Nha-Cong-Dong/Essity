// @vitest-environment jsdom
// DESIGN-W0: the card band of the Kho. Geometry (scroll-snap, 380px slides) is e2e's job; here: the
// accessible shape, the two buttons and their end stops, "i / n", the arrow keys, smooth scroll
// unless reduced motion.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Carousel } from "@/components/ui/carousel";

const scrollTo = vi.fn();

function media(matches: boolean) {
  return (q: string) => ({ matches, media: q, addEventListener() {}, removeEventListener() {} });
}

function band(n = 3) {
  return render(
    <Carousel label="Thẻ của buổi học">
      {Array.from({ length: n }, (_, i) => (
        <article key={i}>Thẻ {i + 1}</article>
      ))}
    </Carousel>,
  );
}

const prevButton = () => screen.getByRole("button", { name: "Thẻ trước" }) as HTMLButtonElement;
const nextButton = () => screen.getByRole("button", { name: "Thẻ sau" }) as HTMLButtonElement;
const trackEl = () => document.querySelector('[data-slot="carousel-track"]') as HTMLElement;

beforeEach(() => {
  scrollTo.mockReset();
  HTMLElement.prototype.scrollTo = scrollTo as unknown as typeof HTMLElement.prototype.scrollTo;
  vi.stubGlobal("matchMedia", media(false));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Carousel", () => {
  it("is a named region with one group per card and the position as meta", () => {
    band();
    expect(screen.getByRole("region", { name: "Thẻ của buổi học" })).toBeTruthy();
    expect(screen.getAllByRole("group")).toHaveLength(3);
    expect(screen.getByText("1 / 3")).toBeTruthy();
  });

  it("both buttons are 44px round and named; 'Thẻ trước' is off at the start", () => {
    band();
    expect(prevButton().className).toMatch(/size-11/);
    expect(prevButton().className).toMatch(/rounded-full/);
    expect(prevButton().disabled).toBe(true);
    expect(nextButton().disabled).toBe(false);
  });

  it("next and previous move one card, update the meta, and stop at the ends", () => {
    band();
    fireEvent.click(nextButton());
    expect(screen.getByText("2 / 3")).toBeTruthy();
    expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ behavior: "smooth" }));
    fireEvent.click(nextButton());
    expect(screen.getByText("3 / 3")).toBeTruthy();
    expect(nextButton().disabled).toBe(true);
    expect(prevButton().disabled).toBe(false);
    fireEvent.click(prevButton());
    expect(screen.getByText("2 / 3")).toBeTruthy();
  });

  it("left and right arrows on the focused track move between cards, never past the ends", () => {
    band();
    expect(trackEl().tabIndex).toBe(0);
    fireEvent.keyDown(trackEl(), { key: "ArrowLeft" });
    expect(screen.getByText("1 / 3")).toBeTruthy();
    for (let i = 0; i < 3; i++) fireEvent.keyDown(trackEl(), { key: "ArrowRight" });
    expect(screen.getByText("3 / 3")).toBeTruthy();
    fireEvent.keyDown(trackEl(), { key: "ArrowLeft" });
    expect(screen.getByText("2 / 3")).toBeTruthy();
  });

  it("arrows typed inside a card's own field are left to that field", () => {
    render(
      <Carousel label="Thẻ">
        <input aria-label="Sửa thẻ" />
        <p>Thẻ 2</p>
      </Carousel>,
    );
    fireEvent.keyDown(screen.getByLabelText("Sửa thẻ"), { key: "ArrowRight" });
    expect(screen.getByText("1 / 2")).toBeTruthy();
  });

  it("scrolls instantly under prefers-reduced-motion", () => {
    vi.stubGlobal("matchMedia", media(true));
    band();
    fireEvent.click(nextButton());
    expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ behavior: "auto" }));
  });

  it("one card: both buttons are off; no cards: 0 / 0", () => {
    band(1);
    expect(prevButton().disabled).toBe(true);
    expect(nextButton().disabled).toBe(true);
    cleanup();
    band(0);
    expect(screen.getByText("0 / 0")).toBeTruthy();
  });

  it("the track is a snap-x mandatory strip with a 16px gap, items aligned to the top", () => {
    band();
    for (const c of ["snap-x", "snap-mandatory", "gap-4", "overflow-x-auto", "items-start"]) {
      expect(trackEl().className).toContain(c);
    }
  });
});
