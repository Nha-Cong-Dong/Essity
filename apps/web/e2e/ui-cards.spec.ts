// UI-1b: a sheet on the cover has a hairline and no shadow, no dog-ear is drawn, a secondary is never
// taller than the primary. Also takes the "after" screenshots (360, 768, 1280) into .work/T7.22/shots.
import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { settled } from "./ready";

const SHOTS = path.resolve(process.cwd(), "../../.work/T7.22/shots");
const WIDTHS = [360, 768, 1280];
const SCREENS = [
  ["cover", "/design-preview"],
  ["today", "/design-preview/today"],
  ["subjects", "/design-preview/subjects"],
] as const;

test.beforeAll(() => mkdirSync(SHOTS, { recursive: true }));

test("the label on the cover has a hairline and no shadow; no dog-ear", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/design-preview");
  await settled(page);
  const label = await page.locator("[class*=label]").first().evaluate((el) => {
    const css = getComputedStyle(el);
    return { shadow: css.boxShadow, border: css.borderTopWidth };
  });
  expect(label.shadow).toBe("none");
  expect(label.border).toBe("1px");
  await expect(page.locator('[data-motif="fold"]')).toHaveCount(0);
});

test("on the today preview no secondary button is taller than the primary", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/design-preview/today");
  await settled(page);
  const heights = await page.locator('main [data-slot="button"]').evaluateAll((els) =>
    els.map((el) => ({ kind: el.getAttribute("data-variant"), h: el.getBoundingClientRect().height })),
  );
  const primary = Math.max(0, ...heights.filter((b) => b.kind?.startsWith("primary")).map((b) => b.h));
  for (const b of heights.filter((x) => x.kind === "secondary")) expect(b.h).toBeLessThanOrEqual(primary || 52);
});

for (const [name, url] of SCREENS) {
  for (const width of WIDTHS) {
    test(`after shot ${name} ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(url);
      await settled(page);
      await page.screenshot({ path: path.join(SHOTS, `after-${name}-${width}.png`), fullPage: true });
    });
  }
}
