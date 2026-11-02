// T2.3c tester (R44): the layout spec measures rows at rest; here the same rows with the edit form
// and the delete confirmation open, at the narrow widths. Geometry only, as in layout.spec.ts.
import { expect, type Locator, type Page, test } from "@playwright/test";

import { settled } from "./ready";

const PAGE = "/design-preview/subjects";
const WIDTHS = [320, 390];

async function open(page: Page, width: number) {
  await page.setViewportSize({ width, height: 900 });
  expect((await page.goto(PAGE))?.status()).toBe(200);
  await settled(page);
}

const noPageScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

/** Every box of `inner` lies within the row, so nothing the open form draws spills sideways. */
async function withinRow(row: Locator, inner: Locator) {
  const r = await row.boundingBox();
  if (r === null) throw new Error("no row box");
  for (const el of await inner.all()) {
    const b = await el.boundingBox();
    if (b === null) continue;
    expect(b.x, await el.evaluate((n) => n.outerHTML.slice(0, 120))).toBeGreaterThanOrEqual(r.x - 0.5);
    expect(b.x + b.width).toBeLessThanOrEqual(r.x + r.width + 0.5);
  }
}

for (const width of WIDTHS) {
  // Red when: the form or its buttons are given a fixed width (or the row grid loses `minmax(0, 1fr)`)
  // so that the open row is wider than the screen, or the long unbroken name stops wrapping once
  // "Sửa" has left the grid.
  test(`R44-k the edit form of the long-word row stays inside the row and the page @ ${width}px`, async ({ page }) => {
    await open(page, width);
    const row = page.locator("main li").nth(2);
    await row.getByRole("button", { name: /^Sửa / }).click();
    await expect(row.getByLabel("Môn")).toBeVisible();
    await withinRow(row, row.locator("input, button, p:not(.sr-only)"));
    expect(await noPageScroll(page)).toBe(true);
  });

  // Red when: the confirmation (a flex-col with max-w-120) or the name column loses its shrink at
  // narrow widths; the long name stays in the same grid above it.
  test(`R44-k the delete confirmation stays inside the row and the page @ ${width}px`, async ({ page }) => {
    await open(page, width);
    const row = page.locator("main li").nth(1);
    await row.getByRole("button", { name: /^Sửa / }).click();
    await row.getByRole("button", { name: "Xóa môn" }).click();
    await expect(row.getByRole("button", { name: "Giữ môn" })).toBeFocused();
    await withinRow(row, row.locator("button, p:not(.sr-only)"));
    expect(await noPageScroll(page)).toBe(true);
  });

  // Red when: opening "Sửa" leaves the button in the grid (it must leave, or the name and the date
  // line would keep sharing a row with a control that is no longer there).
  test(`R44-k while editing, the Sửa button is gone and the name keeps the full first line @ ${width}px`, async ({ page }) => {
    await open(page, width);
    const row = page.locator("main li").first();
    const name = row.locator('a[id$="-name"]');
    const before = await name.boundingBox();
    await row.getByRole("button", { name: /^Sửa / }).click();
    await expect(row.getByRole("button", { name: /^Sửa / })).toHaveCount(0);
    const after = await name.boundingBox();
    expect(before).not.toBeNull();
    expect(after).not.toBeNull();
    expect(after!.x).toBeCloseTo(before!.x, 0);
    expect(after!.y).toBeCloseTo(before!.y, 0);
  });
}
