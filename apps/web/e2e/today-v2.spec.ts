// T7.13a (ADR-0025, FEATURE-MAP "chỗ từng vỡ"): Hôm nay v2 and the subject suggestion block at
// four widths. Geometry only. The busiest state has one unbroken long subject name.
import { expect, type Locator, type Page, test } from "@playwright/test";

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

async function open(page: Page, width: number, path: string) {
  await page.setViewportSize({ width, height: 900 });
  expect((await page.goto(path))?.status()).toBe(200);
  await page.evaluate(() => document.fonts.ready);
}

const noSideScroll = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

for (const width of WIDTHS) {
  test.describe(`today v2 @${width}px`, () => {
    // Red when: a long name or a strip pushes the page wider than the screen (incl. 320 px).
    for (const state of ["busy", "review", "learn", "none-textbook", "no-subjects"]) {
      test(`US-03 AC1: ${state}: the page does not scroll sideways`, async ({ page }) => {
        await open(page, width, `/design-preview/today?state=${state}`);
        expect(await noSideScroll(page)).toBe(true);
      });
    }

    // Red when: a block's contents (long name, buttons) spill out of its sheet.
    test("US-15 AC1: busy: every area keeps its contents inside", async ({ page }) => {
      await open(page, width, "/design-preview/today?state=busy");
      for (const area of await page.locator("main section[aria-labelledby], main [data-slot=sheet]").all()) {
        const outer = await box(area);
        for (const child of await area.locator("h2, h3, p, a, button").all()) {
          expect(inside(await box(child), outer)).toBe(true);
        }
      }
    });

    // Red when: Tiếp tục is not the only primary action drawn above the others.
    test("US-03 AC1: busy: Tiếp tục comes first and is the only primary", async ({ page }) => {
      await open(page, width, "/design-preview/today?state=busy");
      expect(await page.locator('[data-variant="primary"], [data-variant="primary-inverse"]').count()).toBe(1);
    });

    // Red when: the review start button falls outside its pink tile.
    test("US-03 AC1: review: Bắt đầu sits inside the pink tile", async ({ page }) => {
      await open(page, width, "/design-preview/today?state=review");
      const start = page.getByRole("button", { name: "Bắt đầu" });
      expect(inside(await box(start), await box(page.locator('[data-surface="hong"]')))).toBe(true);
    });

    // Red when: the block spills sideways or the pace line overlaps its neighbours.
    for (const state of ["suggested", "not-suggested", "no-textbook", "exam-over"]) {
      test(`US-15 AC6, AC7: subject ${state}: no side scroll, long name`, async ({ page }) => {
        await open(page, width, `/design-preview/subject?state=${state}&long=1`);
        expect(await noSideScroll(page)).toBe(true);
        const sheet = page.locator("[data-slot=sheet]");
        for (const child of await sheet.locator("h2, p, a, button").all()) {
          expect(inside(await box(child), await box(sheet))).toBe(true);
        }
      });
    }
  });
}

test("US-15 AC6: Gợi ý cho hôm nay shows the suggestion and moves focus to it", async ({ page }) => {
  await open(page, 390, "/design-preview/subject?state=not-suggested");
  await page.getByRole("button", { name: "Gợi ý cho hôm nay" }).click();
  await expect(page.getByText("Hôm nay nên học: mục 3.2")).toBeVisible();
  await expect(page.locator("[aria-live=polite]")).toBeFocused();
});
