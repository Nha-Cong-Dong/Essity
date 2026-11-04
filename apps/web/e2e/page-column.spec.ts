// UI-1a (V21): one left edge. On every screen inside AppShell the h1 starts right of the spine, at the
// same x, at 1280px; nothing overflows sideways at 320px; a long Vietnamese title wraps and stays inside.
// Geometry only, on the design-preview pages (they draw the same screens as the real routes).
import { expect, test } from "@playwright/test";

import { settled } from "./ready";

const PAGES = [
  "/design-preview/subjects",
  "/design-preview/subject",
  "/design-preview/today",
  "/design-preview/stats",
  "/design-preview/syllabus",
  "/design-preview/practice-live",
];

for (const url of PAGES) {
  test(`${url}: h1 starts beside the spine at 1280px`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(url);
    await settled(page);
    // V21: the logo is in the 96px spine; every h1 starts right of it, at the page container's edge.
    const spine = await page.getByRole("navigation", { name: "Chính" }).boundingBox();
    const h1 = await page.locator("main h1").first().boundingBox();
    expect(spine && h1).toBeTruthy();
    expect(h1!.x).toBeGreaterThanOrEqual(spine!.x + spine!.width - 1);
  });

  test(`${url}: no sideways overflow at 320px`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 700 });
    await page.goto(url);
    await settled(page);
    const wide = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(wide).toBeLessThanOrEqual(0);
  });
}

test("a long Vietnamese title wraps inside the column at 320px", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await page.goto("/design-preview/subjects");
  await settled(page);
  await page.evaluate(() => {
    const h1 = document.querySelector("main h1");
    if (h1) h1.textContent = "Nghiên cứu khoa học giáo dục và phương pháp luận nghiên cứu định lượng";
  });
  const box = await page.locator("main h1").first().boundingBox();
  expect(box!.x + box!.width).toBeLessThanOrEqual(320);
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(wide).toBeLessThanOrEqual(0);
});

// V22: the rail is as tall as the window from 1024px, so its right border runs the full height.
test("the rail is window-high at 1440px", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/design-preview/subjects");
  await settled(page);
  const rail = await page.locator("header").first().boundingBox();
  expect(rail?.height).toBeGreaterThanOrEqual(899);
});
