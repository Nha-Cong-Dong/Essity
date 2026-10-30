// T8.7a (US-16, US-17; DESIGN §6.12): the Luyện tập screen at four widths. Geometry only. The
// busiest state has one unbroken long type name.
import { expect, type Locator, type Page, test } from "@playwright/test";

const WIDTHS = [320, 390, 768, 1440];
const STATES = [
  "home", "imported", "no-bank", "importing", "empty-ready", "candidates", "no-candidates", "quota",
  "removed", "result", "loading", "error",
];

type Box = { x: number; y: number; width: number; height: number };

async function box(locator: Locator): Promise<Box> {
  const found = await locator.boundingBox();
  if (found === null) throw new Error("no box");
  return found;
}

const inside = (inner: Box, outer: Box) =>
  inner.x >= outer.x - 0.5 &&
  inner.x + inner.width <= outer.x + outer.width + 0.5;

async function open(page: Page, width: number, path: string) {
  await page.setViewportSize({ width, height: 900 });
  expect((await page.goto(path))?.status()).toBe(200);
  await page.evaluate(() => document.fonts.ready);
}

const noSideScroll = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

for (const width of WIDTHS) {
  test.describe(`practice @${width}px`, () => {
    // Red when: a long type name or a row pushes the page wider than the screen (incl. 320 px).
    for (const state of STATES) {
      test(`US-16 AC1: ${state}: the page does not scroll sideways`, async ({ page }) => {
        await open(page, width, `/design-preview/practice?state=${state}`);
        expect(await noSideScroll(page)).toBe(true);
      });
    }

    // Red when: a row's contents (long summary, buttons) spill out of the column, or a button is under 44 px tall.
    test("US-16 AC3: home: every row keeps its contents in the column and buttons are tappable", async ({ page }) => {
      await open(page, width, "/design-preview/practice?state=home");
      const column = await box(page.locator("main h1"));
      for (const row of await page.locator("[data-question]").all()) {
        const outer = await box(row);
        expect(outer.x + outer.width).toBeLessThanOrEqual(width + 0.5);
        for (const child of await row.locator("p, a, button").all()) {
          expect(inside(await box(child), outer)).toBe(true);
        }
        for (const button of await row.locator("button, a[role=button]").all()) {
          expect((await box(button)).height).toBeGreaterThanOrEqual(43.5);
        }
      }
      expect(column.x).toBeGreaterThanOrEqual(0);
    });

    // Red when: the long type name breaks out of its section.
    test("US-16 AC2: home: the long type name wraps inside its section", async ({ page }) => {
      await open(page, width, "/design-preview/practice?state=home");
      const section = page.locator("section[aria-labelledby=g-g1]");
      expect(inside(await box(section.locator("h2")), await box(section))).toBe(true);
    });

    // Red when: the candidate sheet or its buttons spill sideways.
    test("US-17 AC5: candidates: the sheet keeps its contents inside", async ({ page }) => {
      await open(page, width, "/design-preview/practice?state=candidates");
      const sheet = page.locator("[data-candidates]");
      for (const child of await sheet.locator("h3, p, a, button").all()) {
        expect(inside(await box(child), await box(sheet))).toBe(true);
      }
    });
  });
}

test("US-16 AC3: remove puts focus on Hoàn tác and undo puts it back", async ({ page }) => {
  await open(page, 390, "/design-preview/practice?state=home");
  await page.locator("[data-question=q12]").getByRole("button", { name: "Gỡ khỏi luyện tập" }).click();
  await expect(page.getByRole("button", { name: "Hoàn tác" })).toBeFocused();
  await page.getByRole("button", { name: "Hoàn tác" }).click();
  await expect(page.locator("[data-question=q12]").getByRole("button", { name: "Làm câu này" })).toBeFocused();
});
