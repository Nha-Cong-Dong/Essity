// @vitest-environment jsdom
// DOODLE-ICONS: <Doodle> draws the hand-drawn set inline, in currentColor, decorative by default.
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Doodle, DOODLE_NAMES } from "@/components/icons/doodle";
import { NAV } from "@/components/main-nav";

afterEach(cleanup);

describe("Doodle", () => {
  it("has all 25 icons keyed by ASCII Vietnamese names", () => {
    expect(DOODLE_NAMES).toHaveLength(25);
    expect(DOODLE_NAMES).toContain("sach-mo");
    expect(DOODLE_NAMES).toContain("vong-khoanh");
  });

  it("is decorative by default and draws in currentColor", () => {
    const { container } = render(<Doodle name="sao" />);
    const svg = container.querySelector("svg")!;
    expect(svg.getAttribute("aria-hidden")).toBe("true");
    expect(svg.getAttribute("role")).toBeNull();
    expect(svg.getAttribute("stroke")).toBe("currentColor");
    expect(svg.getAttribute("width")).toBe("24");
    expect(svg.querySelectorAll("path").length).toBeGreaterThan(0);
  });

  it("becomes an image when given a title", () => {
    const { getByRole } = render(<Doodle name="lich" title="Lịch" size={20} />);
    const img = getByRole("img", { name: "Lịch" });
    expect(img.getAttribute("aria-hidden")).toBeNull();
    expect(img.getAttribute("width")).toBe("20");
  });

  it("uses finer art above 32px and the -24 art below", () => {
    const small = render(<Doodle name="lich" size={24} />).container.querySelector("svg")!;
    const big = render(<Doodle name="lich" size={48} />).container.querySelector("svg")!;
    expect(small.getAttribute("stroke-width")).toBe("4");
    expect(big.getAttribute("stroke-width")).toBe("3");
    expect(big.querySelectorAll("circle").length).toBeGreaterThan(small.querySelectorAll("circle").length - 1);
  });

  it("never emits ids, so copies on one page cannot clash", () => {
    const { container } = render(
      <>
        {DOODLE_NAMES.map((n) => (
          <Doodle key={n} name={n} />
        ))}
        <Doodle name="may" />
      </>,
    );
    expect(container.querySelectorAll("[id]")).toHaveLength(0);
    expect(container.querySelectorAll("svg")).toHaveLength(26);
  });

  it("main nav items name a doodle each", () => {
    for (const item of NAV) expect(DOODLE_NAMES).toContain(item.doodle);
  });
});
