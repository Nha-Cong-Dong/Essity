// T2.15, T2.16 (ADR-0025): the answer and result screen at four widths, on /design-preview/review
// (a long subject name, a long prompt, long words in the answer and the result). Geometry only:
// nothing spills, the two columns sit side by side from 901px and stack below.
import { expect, type Locator, type Page, test } from "@playwright/test";

import { settled } from "./ready";

const PAGE = "/design-preview/review";
const WIDTHS = [320, 390, 768, 1440];

type Box = { x: number; y: number; width: number; height: number };

async function box(locator: Locator): Promise<Box> {
  const found = await locator.boundingBox();
  if (found === null) throw new Error("no box");
  return found;
}

const sideways = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);

async function open(page: Page, width: number) {
  await page.setViewportSize({ width, height: 900 });
  expect((await page.goto(PAGE))?.status()).toBe(200);
  await settled(page);
  await expect(page.getByLabel("Câu trả lời của bạn")).toBeVisible();
}

for (const width of WIDTHS) {
  test.describe(`@${width}px`, () => {
    test.beforeEach(async ({ page }) => open(page, width));

    // Red when: the long subject name, prompt or draft pushes the page wider than the screen.
    test("answering: the page does not scroll sideways, Gửi and Không nhớ are on screen", async ({ page }) => {
      expect(await sideways(page)).toBe(false);
      for (const name of ["Gửi", "Không nhớ", "Dừng tại đây"]) {
        const button = await box(page.getByRole("button", { name }));
        expect(button.x).toBeGreaterThanOrEqual(0);
        expect(button.x + button.width).toBeLessThanOrEqual(width);
      }
    });

    // Red when: the result column is laid over the question, or stays beside it on a phone.
    test("the result: beside the answer from 901px, under it below; nothing spills", async ({ page }) => {
      await page.getByRole("button", { name: "Gửi" }).click();
      await expect(page.locator("[data-verdict]")).toBeVisible();
      await page.waitForTimeout(800); // the rise and sweep have ended
      expect(await sideways(page)).toBe(false);
      const question = await box(page.getByRole("heading", { level: 1 }));
      const verdict = await box(page.locator("[data-verdict]"));
      if (width >= 901) {
        expect(verdict.x).toBeGreaterThan(question.x + question.width);
      } else {
        expect(verdict.y).toBeGreaterThan(question.y + question.height);
      }
      const next = await box(page.getByRole("button", { name: "Câu tiếp" }));
      expect(next.x + next.width).toBeLessThanOrEqual(width);
      await expect(page.getByRole("button", { name: "Câu tiếp" })).toBeFocused();
    });
  });
}
