// UI-1a: one left edge. On every screen inside AppShell the h1 starts at the same x as the logo,
// at 1280px; nothing overflows sideways at 320px; a long Vietnamese title wraps and stays inside.
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
  test(`${url}: h1 starts under the logo at 1280px`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(url);
    await settled(page);
    const logo = await page.locator("header").getByText("Essity", { exact: true }).boundingBox();
    const h1 = await page.locator("main h1").first().boundingBox();
    expect(logo && h1).toBeTruthy();
    expect(Math.abs(h1!.x - logo!.x)).toBeLessThanOrEqual(1);
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
