// T7.5a (US-13 AC4, AC5, AC8, AC9; US-01 AC4): the Đề cương screen and the role picker at four
// widths. Geometry and colour only. `long-titles` has an unbroken word, `deep` six levels.
import { expect, type Locator, type Page, test } from "@playwright/test";

import { settled } from "./ready";

const WIDTHS = [320, 390, 768, 1440];
const STATES = [
  "ready", "provisional", "provisional-scan", "extracting", "empty-no-main", "flat-pptx", "editing", "range-error",
  "parent-panel", "save-error", "loading", "error", "long-titles", "deep",
  "upload-empty", "upload-files", "upload-main-exists", "upload-rename", "upload-rejected", "upload-uploading",
];

type Box = { x: number; y: number; width: number; height: number };

async function box(locator: Locator): Promise<Box> {
  const found = await locator.boundingBox();
  if (found === null) throw new Error("no box");
  return found;
}

const inside = (inner: Box, outer: Box) => inner.x >= outer.x - 0.5 && inner.x + inner.width <= outer.x + outer.width + 0.5;

async function open(page: Page, width: number, path: string) {
  await page.setViewportSize({ width, height: 900 });
  expect((await page.goto(path))?.status()).toBe(200);
  await settled(page);
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

for (const width of WIDTHS) {
  test.describe(`syllabus @${width}px`, () => {
    // Red when: a long title, a deep level, the ⋯ button or a pill row pushes the page wider than the screen (incl. 320 px).
    for (const state of STATES) {
      test(`US-13 AC4: ${state}: the page does not scroll sideways`, async ({ page }) => {
        await open(page, width, `/design-preview/syllabus?state=${state}`);
        expect(await noSideScroll(page)).toBe(true);
      });
    }

    // Red when: a long title or an unbroken word spills out of its row, or a row is under 44 px tall.
    test("US-13 AC4: long-titles: every title stays inside its row and rows are tappable", async ({ page }) => {
      await open(page, width, "/design-preview/syllabus?state=long-titles");
      await page.locator("[data-node='2']").locator("[data-row]").first().click();
      for (const row of await page.locator("[data-row]").all()) {
        const outer = await box(row);
        expect(outer.x + outer.width).toBeLessThanOrEqual(width + 0.5);
        expect(outer.height).toBeGreaterThanOrEqual(43.5);
        for (const title of await row.locator("[id$='-t']").all()) {
          expect(inside(await box(title), outer)).toBe(true);
        }
      }
    });

    // Red when: at 320 px the indent leaves too little room for a title (the real indent stops at level 3 there).
    test("US-13 AC4: deep: a level-6 title keeps at least 140 px", async ({ page }) => {
      await open(page, width, "/design-preview/syllabus?state=deep");
      for (const id of ["5", "5.1", "5.1.1", "5.1.1.1", "5.1.1.1.1"]) {
        const row = page.locator(`[data-node='${id}']`);
        if ((await row.count()) && (await row.getAttribute("aria-expanded")) === "false") await row.locator("[data-row]").first().click();
      }
      const title = page.locator("[data-node='5.1.1.1.1.1'] [id$='-t']");
      expect((await box(title)).width).toBeGreaterThanOrEqual(140);
    });

    // Red when: the chevron or ⋯ touch area is under 44 px (the visible mark is 28 px).
    test("US-13 AC4: chevron and ⋯ have a 44 px touch area", async ({ page }) => {
      await open(page, width, "/design-preview/syllabus?state=ready");
      for (const selector of ["[data-chevron]", "[data-more]"]) {
        const button = page.locator(selector).first();
        const size = await button.evaluate((el) => {
          const style = getComputedStyle(el, "::after");
          return { width: parseFloat(style.width), height: parseFloat(style.height) };
        });
        expect(size.width).toBeGreaterThanOrEqual(43.5);
        expect(size.height).toBeGreaterThanOrEqual(43.5);
      }
    });

    // Red when: "chưa học" is drawn in a warning colour (it is only the absence of a mark).
    test("US-13 AC5: a not-yet-studied row is in plain ink, never red", async ({ page }) => {
      await open(page, width, "/design-preview/syllabus?state=ready");
      const colour = await page.locator("[data-node='2.3'] [id$='-t']").evaluate((el) => getComputedStyle(el).color);
      const [r, g, b] = colour.match(/[\d.]+/g)!.map(Number);
      expect(r > 150 && g < 90 && b < 90).toBe(false);
    });

    // Red when: the role pills, the swap box or the buttons spill sideways.
    test("US-01 AC4: upload-main-exists: pills and the swap box stay inside the column", async ({ page }) => {
      await open(page, width, "/design-preview/syllabus?state=upload-main-exists");
      const row = page.locator("li[data-file]").first();
      const outer = await box(row);
      for (const child of await row.locator("label, p, button").all()) {
        expect(inside(await box(child), outer)).toBe(true);
      }
      for (const pill of await row.locator("label").all()) {
        expect((await box(pill)).height).toBeGreaterThanOrEqual(43.5);
      }
    });
  });
}

// Red when: the tree is not on the first screen of a phone at 360x640 in the provisional state.
test("US-13 AC9: provisional at 360x640 shows the first tree row without scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 640 });
  expect((await page.goto("/design-preview/syllabus?state=provisional"))?.status()).toBe(200);
  await page.evaluate(() => document.fonts.ready);
  const first = await box(page.locator("[role=treeitem]").first());
  expect(first.y + first.height).toBeLessThanOrEqual(640);
});

test("US-13 AC4: Tab reaches the tree once, the arrows move inside, Enter on a leaf puts focus in the panel", async ({ page }) => {
  await open(page, 1440, "/design-preview/syllabus?state=ready");
  await page.locator("[role=tree] [role=treeitem]").first().focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.locator("[role=treeitem]:focus")).toHaveCount(1);
  await page.locator("[data-node='2.3']").focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("[data-panel='2.3'] button").first()).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.locator("[data-node='2.3']")).toBeFocused();
});
