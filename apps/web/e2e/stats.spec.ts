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
    test("US-10 AC1: many-subjects: every total tile keeps its contents inside", async ({ page }) => {
      await open(page, width, "/design-preview/stats?state=many-subjects");
      for (const block of await page.locator("[data-kpi]").all()) {
        const outer = await box(block);
        expect(outer.x + outer.width).toBeLessThanOrEqual(width + 0.5);
        for (const child of await block.locator("p").all()) {
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
test("US-10 AC4: mouse cells stretch to the sheet (12-28 px, square) with 4 px between them", async ({ page }) => {
  await open(page, 1440, "/design-preview/stats?state=full-year");
  const a = await box(page.locator('[data-day="2026-10-26"]'));
  const b = await box(page.locator('[data-day="2026-10-27"]'));
  expect(a.width).toBeGreaterThanOrEqual(12);
  expect(a.width).toBeLessThanOrEqual(28.5);
  expect(a.height).toBeCloseTo(a.width, 0);
  expect(b.y - (a.y + a.height)).toBeCloseTo(4, 0);
});

test("US-10 AC4: tapping a day pins it and the panel names it", async ({ page }) => {
  await open(page, 390, "/design-preview/stats?state=full-year");
  await page.locator('[data-day="2026-10-27"]').click();
  await expect(page.locator("[data-day-detail]")).toContainText("Thứ ba, 27/10");
  await page.getByRole("button", { name: "Ngày sau" }).click();
  await expect(page.locator("[data-day-detail]")).toContainText("Thứ tư, 28/10");
});

// I1, I2. Red when: a per-subject block or filter comes back, or a weekday label is missing.
test("I1, I2: overall totals only, and all seven weekday labels on the year grid", async ({ page }) => {
  await open(page, 1440, "/design-preview/stats?state=full-year");
  await expect(page.locator("[data-subject-block]")).toHaveCount(0);
  await expect(page.locator("#stats-subject")).toHaveCount(0);
  await expect(page.locator("[data-kpi]")).toHaveCount(3);
  const grid = page.locator("[data-activity-grid]");
  for (const day of ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]) await expect(grid).toContainText(day);
});

// T9.5. Red when: the third nav item is missing, or the current page is not marked "Thống kê".
test("US-10 AC1: the nav has Thống kê and marks it current", async ({ page }) => {
  await open(page, 390, "/design-preview/stats?state=full-year");
  const nav = page.getByRole("navigation", { name: "Chính" });
  await expect(nav.getByRole("link")).toHaveText(["Hôm nay", "Môn học", "Kho kiến thức", "Đồ thị", "Thống kê"]);
  await expect(nav.locator('[aria-current="page"]')).toHaveText("Thống kê");
  expect(await nav.getByRole("link", { name: "Thống kê" }).getAttribute("href")).toBe("/stats");
});

// Red when: the CSV button is a dead link instead of the download route (AC8).
test("US-10 AC8: the CSV button points at /api/export", async ({ page }) => {
  await open(page, 1440, "/design-preview/stats?state=full-year");
  const link = page.locator('main a[href="/api/export"]');
  await expect(link).toHaveText("Tải dữ liệu (CSV)");
  await expect(link).toHaveAttribute("download", "");
});

// Red when: the live route lets a visitor without a session in (the proxy only checks the cookie).
test("US-10: /stats without a session goes to the login page", async ({ page }) => {
  await page.goto("/stats");
  await expect(page).toHaveURL(/\/login/);
});

// Red when: on a wide screen the three numbers (UI-A) do not sit in one row, lead first.
test("I1: on a wide screen the three numbers sit in one row", async ({ page }) => {
  await open(page, 1440, "/design-preview/stats?state=full-year");
  const [lead, a, b] = await Promise.all((await page.locator("[data-kpi]").all()).map((t) => box(t)));
  expect(Math.abs(lead.y - a.y)).toBeLessThan(2);
  expect(Math.abs(a.y - b.y)).toBeLessThan(2);
  expect(a.x).toBeGreaterThan(lead.x + lead.width - 1);
  expect(b.x).toBeGreaterThan(a.x + a.width - 1);
});
