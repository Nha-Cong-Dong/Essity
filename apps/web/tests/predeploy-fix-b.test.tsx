// @vitest-environment jsdom
// PREDEPLOY-FIX-B: layout fixes E-04, E-05, E-09, E-10 (structure and class assertions; the
// overflow itself is measured by the e2e scenarios in .work/PREDEPLOY-E2E).
import { cleanup, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SubjectStatsBlock } from "@/components/subjects/subject-stats-block";
import { UploadStep } from "@/components/subjects/upload-step";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

afterEach(cleanup);
const src = (p: string) => readFileSync(join(__dirname, "..", p), "utf8");

describe("E-04 /upload tabs fit 390 px", () => {
  it("the three tabs share the row (grid of 3), none is shrink-0 / nowrap / scrolling", () => {
    render(<UploadStep name="Xác suất" subjectId="s1" />);
    const list = screen.getByRole("tablist");
    expect(list.className).toContain("grid-cols-3");
    expect(list.className).not.toContain("overflow-x-auto");
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(3);
    for (const t of tabs) {
      expect(t.className).toContain("min-w-0");
      expect(t.className).not.toContain("shrink-0");
      expect(t.className).not.toContain("whitespace-nowrap");
    }
  });
});

describe("E-05 no horizontal overflow at 390 px", () => {
  it("the heatmap root can shrink and its scroller is its own box", () => {
    const css = src("components/stats/stats.module.css");
    expect(css).toMatch(/\.root\s*\{[^}]*min-width:\s*0;[^}]*max-width:\s*100%/);
    expect(css).toMatch(/\.scroll\s*\{[^}]*overflow-x:\s*auto/);
  });
  it("stats and graph grids have a shrinkable single column below their breakpoint", () => {
    const stats = src("components/stats/stats-screen.tsx");
    expect(stats.match(/grid grid-cols-\[minmax\(0,1fr\)\]/g)?.length).toBeGreaterThanOrEqual(3);
    expect(src("components/graph/graph-screen.tsx")).toContain("grid grid-cols-[minmax(0,1fr)] items-start");
  });
});

describe("E-09 subject stat tile and outline card", () => {
  it("value and label sit in columns that grow (no overlap), the unit wraps with a gap", () => {
    const stats = { syllabus: { studied: 14, leaves: 83 }, bank: null, retention: null } as never;
    const { container } = render(<SubjectStatsBlock stats={stats} />);
    const dl = container.querySelector("dl")!;
    expect(dl.className).toContain("grid-cols-[minmax(7.5rem,auto)_minmax(0,1fr)]");
    const dd = dl.querySelector("dd")!;
    expect(dd.className).toContain("flex-wrap");
    expect(dd.className).toContain("gap-x-1.5");
    expect(dd.textContent).toBe("14/83phần");
    expect(dl.querySelector("dt")!.textContent).toBe("Đã học");
  });
  it("the outline list keeps room under its last row", () => {
    expect(src("components/subjects/subject-chapters-aside.tsx")).toMatch(/max-h-\[60vh\][^"]*overflow-y-auto pb-3/);
  });
});

describe("E-10 graph is stable and quiet", () => {
  it("no custom wheelSensitivity in either canvas (Cytoscape warns about it)", () => {
    expect(src("components/graph/graph-canvas.tsx")).not.toContain("wheelSensitivity");
    expect(src("components/graph/knowledge-graph.tsx")).not.toContain("wheelSensitivity");
  });
  it("the subject graph starts from a fixed spiral and does not randomize the layout", () => {
    const s = src("components/graph/graph-canvas.tsx");
    expect(s).toContain("position: spiralStart(i)");
    expect(s).toMatch(/randomize: false/);
    expect(s).not.toMatch(/randomize: true/);
  });
  it("overlapping labels are pushed apart at every width, not only on phones", () => {
    expect(src("components/graph/graph-canvas.tsx")).not.toMatch(/i < 12 && cy\.width\(\) < 480/);
  });
});
