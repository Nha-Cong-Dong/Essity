// @vitest-environment jsdom
// LOGO-E: the layered-E mark renders four rects with token colours; landing and app header include it.
import { readFileSync } from "node:fs";
import path from "node:path";

import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { BrandMark } from "@/components/brand-mark";

afterEach(cleanup);

describe("BrandMark", () => {
  it("draws the E with ink bars and one accent bar at the requested size", () => {
    const { container } = render(<BrandMark size={40} />);
    const svg = container.querySelector("svg")!;
    expect(svg.getAttribute("viewBox")).toBe("0 0 64 64");
    expect(svg.getAttribute("width")).toBe("40");
    const fills = [...svg.querySelectorAll("rect")].map((r) => r.getAttribute("fill"));
    expect(fills).toEqual(["var(--logo-ink)", "var(--logo-ink)", "var(--logo-accent)", "var(--logo-ink)"]);
  });

  it("is used by the landing and the app header", () => {
    const root = import.meta.dirname + "/..";
    for (const f of ["components/landing/landing.tsx", "components/shells.tsx"]) {
      expect(readFileSync(path.join(root, f), "utf8")).toContain("<BrandMark");
    }
  });
});
