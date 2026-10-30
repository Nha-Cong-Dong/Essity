// T9.10a (US-19 AC3, AC4, AC6; DESIGN §6.15): the Đồ thị screen at six widths, in real Chromium.
// Geometry and the main flow only: Cytoscape draws a real canvas here.
import { expect, type Locator, type Page, test } from "@playwright/test";

import { settled } from "./ready";

const WIDTHS = [320, 359, 360, 390, 768, 1440];
const STATES = ["empty", "few", "many", "filtered", "selected", "long", "loading", "error"];

type Box = { x: number; y: number; width: number; height: number };

async function box(locator: Locator): Promise<Box> {
  const found = await locator.boundingBox();
  if (found === null) throw new Error("no box");
  return found;
}
const inside = (inner: Box, outer: Box) =>
  inner.x >= outer.x - 0.5 && inner.x + inner.width <= outer.x + outer.width + 0.5;

async function open(page: Page, width: number, path: string) {
  await page.setViewportSize({ width, height: 900 });
  expect((await page.goto(path))?.status()).toBe(200);
  await settled(page);
}
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

type CyHost = HTMLDivElement & {
  __cy?: {
    zoom: (z?: number) => number;
    nodes: (s: string) => {
      length: number;
      first: () => { renderedPosition: () => { x: number; y: number }; renderedBoundingBox: () => { w: number; h: number } };
    };
  };
};

for (const width of WIDTHS) {
  test.describe(`graph @${width}px`, () => {
    // Red when: a long title, the chips or the frame push the page wider than the screen.
    for (const state of STATES) {
      test(`US-19 AC3: ${state}: the page does not scroll sideways`, async ({ page }) => {
        await open(page, width, `/design-preview/graph?state=${state}`);
        expect(await noSideScroll(page)).toBe(true);
      });
    }

    test("US-19 AC3: the list form does not scroll sideways either", async ({ page }) => {
      await open(page, width, "/design-preview/graph?state=long&view=list");
      expect(await noSideScroll(page)).toBe(true);
      const tray = await box(page.locator("[data-tray]"));
      for (const child of await page.locator("[data-tray] h2, [data-tray] p, [data-tray] button").all()) {
        if (await child.isVisible()) expect(inside(await box(child), tray)).toBe(true);
      }
    });

    // Red when: a button in the tray, the filters or the frame is under 44 px tall.
    test("US-19 AC3: the controls are 44 px tall", async ({ page }) => {
      await open(page, width, "/design-preview/graph?state=selected");
      await page.locator("[data-kind-filter] summary").click();
      const controls = page.locator("[data-graph-screen] button:visible, [data-graph-screen] summary:visible");
      for (const control of await controls.all()) {
        expect((await box(control)).height).toBeGreaterThanOrEqual(43.5);
      }
      for (const chip of await page.locator("[data-slot='filter-chip']").all()) {
        expect((await box(chip)).height).toBeGreaterThanOrEqual(43.5);
      }
    });

    // Red when: the frame is missing at this width, or it is taller than the first screen holds.
    test("US-19 AC3: the frame is seen without scrolling a long way", async ({ page }) => {
      await open(page, width, "/design-preview/graph?state=few");
      const frame = await box(page.locator("[data-graph-canvas]"));
      expect(frame.y).toBeLessThan(600);
      expect(frame.width).toBeGreaterThan(Math.min(width - 40, 280));
    });
  });
}

// Red when: a card's hit box is under 44 px at the start or after zooming out.
test("US-19 AC3: a card is hit as 44 px at any zoom", async ({ page }) => {
  await open(page, 390, "/design-preview/graph?state=few");
  const read = () =>
    page.locator("[data-graph-canvas]").evaluate((el) => {
      const cy = (el as CyHost).__cy!;
      const b = cy.nodes(".card").first().renderedBoundingBox();
      return { w: b.w, h: b.h, zoom: cy.zoom() };
    });
  await expect.poll(async () => (await read()).w).toBeGreaterThan(0);
  const first = await read();
  expect(first.w).toBeGreaterThanOrEqual(43);
  await page.getByRole("button", { name: "Thu nhỏ" }).click();
  await page.getByRole("button", { name: "Thu nhỏ" }).click();
  const zoomed = await read();
  expect(zoomed.zoom).toBeLessThan(first.zoom);
  expect(zoomed.w).toBeGreaterThanOrEqual(43);
});

// Red when: tapping a node in the canvas does not open its card in the tray.
test("US-19 AC4: tapping a node opens its card with the evidence of its links", async ({ page }) => {
  await open(page, 1440, "/design-preview/graph?state=few");
  const canvas = page.locator("[data-graph-canvas]");
  await expect.poll(() => canvas.evaluate((el) => (el as CyHost).__cy?.nodes(".card").length ?? 0)).toBe(5);
  await page.waitForTimeout(500); // layout settles
  const at = await canvas.evaluate((el) => (el as CyHost).__cy!.nodes(".card").first().renderedPosition());
  const frame = await box(canvas);
  await page.mouse.click(frame.x + at.x, frame.y + at.y);
  const tray = page.locator("[data-tray]");
  await expect(tray.locator("h2")).not.toHaveText("Chi tiết");
  await expect(tray).toContainText("Liên kết");
});

// Red when: the keyboard cannot reach the list, choose a card, and land on the tray's heading.
test("US-19 AC3, AC4: the list form works from the keyboard", async ({ page }) => {
  await open(page, 1440, "/design-preview/graph?state=few");
  await page.getByRole("switch", { name: "Xem dạng danh sách" }).focus();
  await page.keyboard.press("Space");
  await expect(page).toHaveURL(/view=list/);
  const list = page.locator("[data-edge-list]");
  await expect(list.locator("tbody tr")).toHaveCount(6);
  await list.getByRole("button", { name: /^Chọn thẻ Bắt tay ba bước/ }).first().focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("[data-tray] h2")).toHaveText("Bắt tay ba bước");
  await expect(page.locator("[data-tray] h2")).toBeFocused();
});

// Red when: the table is not a table from 768 px, or a phone gets the table instead of cards.
test("US-19 AC3: a table from 768 px, a list of cards below", async ({ page }) => {
  await open(page, 768, "/design-preview/graph?state=few&view=list");
  await expect(page.locator("table")).toHaveCount(1);
  await open(page, 390, "/design-preview/graph?state=few&view=list");
  await expect(page.locator("table")).toHaveCount(0);
  await expect(page.locator("ul[aria-label='Liên kết giữa các thẻ'] > li")).toHaveCount(6);
});

test("US-19 AC3: many cards: the neutral line, 300 nodes, and a hint to use the list", async ({ page }) => {
  await open(page, 390, "/design-preview/graph?state=many");
  await expect(page.getByText("Hiển thị 300 thẻ đầu của mục này. Chọn mục nhỏ hơn để xem đủ.")).toBeVisible();
  await expect(page.getByText("Nhiều thẻ, chọn qua danh sách sẽ dễ hơn.")).toBeVisible();
  await expect.poll(() => page.locator("[data-graph-canvas]").evaluate((el) => (el as CyHost).__cy?.nodes(".card").length ?? 0)).toBe(300);
});

test("US-19 AC6: the graph is not in the main navigation", async ({ page }) => {
  await open(page, 1440, "/design-preview/graph?state=few");
  for (const link of await page.locator("header a, nav a").all()) {
    expect(await link.getAttribute("href")).not.toMatch(/graph/);
  }
});

// Red when: reduced motion still animates the layout (the canvas must settle at once).
test("DESIGN §6.15: with reduced motion the layout is placed at once", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await open(page, 1440, "/design-preview/graph?state=few");
  const canvas = page.locator("[data-graph-canvas]");
  await expect.poll(() => canvas.evaluate((el) => (el as CyHost).__cy?.nodes(".card").length ?? 0)).toBe(5);
  const a = await canvas.evaluate((el) => (el as CyHost).__cy!.nodes(".card").first().renderedPosition());
  const b = await canvas.evaluate((el) => (el as CyHost).__cy!.nodes(".card").first().renderedPosition());
  expect(b).toEqual(a);
});
