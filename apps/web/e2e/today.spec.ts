// T2.14 (ADR-0025): /today's busiest state at four widths, on /design-preview/today-v1 (the screen /today draws now). Geometry
// only, as in layout.spec.ts: nothing spills, nothing overlaps, the page never scrolls sideways.
import { expect, type Locator, type Page, test } from "@playwright/test";

import { settled } from "./ready";

const PAGE = "/design-preview/today-v1";
const WIDTHS = [320, 390, 768, 1440];

type Box = { x: number; y: number; width: number; height: number };

async function box(locator: Locator): Promise<Box> {
  const found = await locator.boundingBox();
  if (found === null) throw new Error("no box");
  return found;
}

const inside = (inner: Box, outer: Box) =>
  inner.x >= outer.x - 0.5 &&
  inner.y >= outer.y - 0.5 &&
  inner.x + inner.width <= outer.x + outer.width + 0.5 &&
  inner.y + inner.height <= outer.y + outer.height + 0.5;

const overlap = (a: Box, b: Box) =>
  a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;

async function open(page: Page, width: number) {
  await page.setViewportSize({ width, height: 900 });
  expect((await page.goto(PAGE))?.status()).toBe(200);
  await settled(page);
}

for (const width of WIDTHS) {
  test.describe(`@${width}px`, () => {
    test.beforeEach(async ({ page }) => open(page, width));

    // Red when: a tile or the long subject name pushes the page wider than the screen.
    test("the page does not scroll sideways", async ({ page }) => {
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });

    // Red when: "Bắt đầu" falls outside the pink tile it belongs to.
    test("Bắt đầu sits inside the session tile", async ({ page }) => {
      const tile = page.locator('[data-surface="hong"]');
      expect(inside(await box(page.getByRole("button", { name: "Bắt đầu" })), await box(tile))).toBe(true);
    });

    // Red when: the backlog sentence runs into "Ôn thêm" instead of wrapping beside or above it.
    test("the backlog sentence and Ôn thêm do not overlap", async ({ page }) => {
      const sentence = page.getByText(/^Để kịp thi/);
      const more = page.getByRole("button", { name: "Ôn thêm" });
      expect(overlap(await box(sentence), await box(more))).toBe(false);
    });

    // Red when: a long subject name spills out of the subjects tile.
    test("subject names stay inside their tile", async ({ page }) => {
      const tile = page.getByRole("heading", { name: "Môn đang ôn" }).locator("xpath=..");
      for (const item of await tile.getByRole("listitem").all()) {
        expect(inside(await box(item), await box(tile))).toBe(true);
      }
    });
  });
}
