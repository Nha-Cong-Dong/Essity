// T9.5a (US-10 AC1, AC4, AC6; DESIGN §6.13): the Thống kê screen at six widths. Geometry only.
// The busiest states carry one unbroken long subject name and 53 weeks of columns.
import { expect, type Locator, type Page, test } from "@playwright/test";

import { settled } from "./ready";

const WIDTHS = [320, 359, 360, 390, 768, 1440];
const STATES = ["empty", "few-days", "full-year", "many-subjects", "no-exam", "no-bank", "loading", "error"];
// Unicode-safe: \b never matches "trễ" (the T8.7a lesson).
const FORBIDDEN =
  /(?<!\p{L})(streak|chuỗi|xếp hạng|ranking|trễ|kém|lười|bỏ lỡ|thất bại|tụt|hạng|sẵn sàng thi)(?!\p{L})/iu;

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

const noSideScroll = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

for (const width of WIDTHS) {
  test.describe(`stats @${width}px`, () => {
    // Red when: a long subject name, the select or the 53-week grid pushes the page wider than the screen.
    for (const state of STATES) {
      test(`US-10 AC4: ${state}: the page does not scroll sideways`, async ({ page }) => {
        await open(page, width, `/design-preview/stats?state=${state}`);
        expect(await noSideScroll(page)).toBe(true);
      });
    }

    // Red when: a block's contents spill out of it, or the long name leaves its block.
    test("US-10 AC1: many-subjects: every block keeps its contents inside", async ({ page }) => {
      await open(page, width, "/design-preview/stats?state=many-subjects");
      for (const block of await page.locator("[data-subject-block]").all()) {
        const outer = await box(block);
        expect(outer.x + outer.width).toBeLessThanOrEqual(width + 0.5);
        for (const child of await block.locator("h2, p, dt, dd, table, a").all()) {
          if (!(await child.isVisible())) continue;
          expect(inside(await box(child), outer)).toBe(true);
        }
      }
    });

    // Red when: the grid grows the page instead of scrolling inside its own box, or today is out of view.
    test("US-10 AC4: full-year: the grid scrolls inside its box and opens near today", async ({ page }) => {
      await open(page, width, "/design-preview/stats?state=full-year");
      const scroller = page.locator("[data-activity-grid] > div").first();
      expect(inside(await box(scroller), await box(page.locator("#activity")))).toBe(true);
      const metrics = await scroller.evaluate((el) => ({ sw: el.scrollWidth, cw: el.clientWidth }));
      if (width < 1280) expect(metrics.sw).toBeGreaterThan(metrics.cw);
      const today = await box(page.locator("[data-today=true]").first());
      expect(inside(today, await box(scroller))).toBe(true);
    });

    // Red when: the detail panel or its buttons spill, or the day buttons are under 44 px tall.
    test("US-10 AC4: the day panel keeps its contents inside and its buttons are tappable", async ({ page }) => {
      await open(page, width, "/design-preview/stats?state=full-year");
      const panel = page.locator("[data-day-detail]");
      const outer = await box(panel);
      for (const child of await panel.locator("p, button").all()) {
        expect(inside(await box(child), outer)).toBe(true);
      }
      for (const button of await panel.locator("button").all()) {
        expect((await box(button)).height).toBeGreaterThanOrEqual(43.5);
      }
    });

    // Red when: a banned word shows on screen, or a normal state has a primary button.
    test("US-10 AC6, AC7: full-year: no banned word on screen and no primary", async ({ page }) => {
      await open(page, width, "/design-preview/stats?state=full-year");
      const text = await page.evaluate(() => {
        const clone = document.querySelector("main")!.cloneNode(true) as HTMLElement;
        clone.querySelectorAll("[data-user]").forEach((el) => el.remove());
        return clone.textContent ?? "";
      });
      expect(text).not.toMatch(FORBIDDEN);
      expect(await page.locator("main [data-variant=primary]").count()).toBe(0);
    });
  });
}

// Red when: cells touch each other (WCAG 2.5.8 spacing) with a mouse, or are not square.
test("US-10 AC4: mouse cells are 16 px with 6 px between them", async ({ page }) => {
  await open(page, 1440, "/design-preview/stats?state=full-year");
  const a = await box(page.locator('[data-day="2026-10-26"]'));
  const b = await box(page.locator('[data-day="2026-10-27"]'));
  expect(a.width).toBeCloseTo(16, 0);
  expect(a.height).toBeCloseTo(16, 0);
  expect(b.y - (a.y + a.height)).toBeCloseTo(6, 0);
});

test("US-10 AC4: tapping a day pins it and the panel names it", async ({ page }) => {
  await open(page, 390, "/design-preview/stats?state=full-year");
  await page.locator('[data-day="2026-10-27"]').click();
  await expect(page.locator("[data-day-detail]")).toContainText("Thứ ba, 27/10");
  await page.getByRole("button", { name: "Ngày sau" }).click();
  await expect(page.locator("[data-day-detail]")).toContainText("Thứ tư, 28/10");
});

test("US-10 AC4: ?subject= filters the blocks", async ({ page }) => {
  await open(page, 1440, "/design-preview/stats?state=many-subjects&subject=0b8f1d2e-0000-4000-8000-000000000002");
  await expect(page.locator("[data-subject-block]")).toHaveCount(1);
});
