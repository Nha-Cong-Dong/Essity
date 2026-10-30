// T9.3a (US-18 AC1, AC4, AC5, AC8; DESIGN §6.14): the command bar at four widths and with the
// virtual keyboard (360x640). Geometry and a keyboard-only flow; the logic is in vitest.
import { expect, type Locator, type Page, test } from "@playwright/test";

import { settled } from "./ready";

const WIDTHS = [320, 390, 768, 1440];
const STATES = [
  "idle", "understanding", "done", "many", "unclear", "not-allowed", "too-long", "pending-ai",
  "pending-ai-practice", "error", "error-unsure", "undone", "undone-previous", "undo-failed", "long",
];

type Box = { x: number; y: number; width: number; height: number };

async function box(locator: Locator): Promise<Box> {
  const found = await locator.boundingBox();
  if (found === null) throw new Error("no box");
  return found;
}

const inside = (inner: Box, outer: Box) => inner.x >= outer.x - 0.5 && inner.x + inner.width <= outer.x + outer.width + 0.5;

async function open(page: Page, width: number, state: string, height = 900) {
  await page.setViewportSize({ width, height });
  expect((await page.goto(`/design-preview/command-bar?state=${state}`))?.status()).toBe(200);
  await settled(page);
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

for (const width of WIDTHS) {
  test.describe(`command bar @${width}px`, () => {
    // Red when: a long name, a long diff line or the buttons push the page wider than the screen.
    for (const state of STATES) {
      test(`US-18 AC1: ${state}: the page does not scroll sideways`, async ({ page }) => {
        await open(page, width, state);
        expect(await noSideScroll(page)).toBe(true);
      });
    }

    // Red when: a part of the bar or tray spills out of the form, or a button is under 44 px.
    test("US-18 AC4: long: everything stays inside the form and buttons are tappable", async ({ page }) => {
      await open(page, width, "long");
      const form = await box(page.locator("form[data-command-bar]"));
      for (const child of await page.locator("form[data-command-bar] :is(input, p, a, button)").all()) {
        if (!(await child.isVisible())) continue;
        expect(inside(await box(child), form)).toBe(true);
      }
      for (const button of await page.locator("[data-tray] :is(button, a)").all()) {
        expect((await box(button)).height).toBeGreaterThanOrEqual(43.5);
      }
    });

    // Red when: the field or Gửi is under 44 px, or the field is not on one line with Gửi.
    test("US-18 AC1: idle: one line, field and Gửi both tall enough", async ({ page }) => {
      await open(page, width, "idle");
      const input = await box(page.getByLabel("Gõ một lệnh để sửa"));
      const send = await box(page.getByRole("button", { name: "Gửi" }));
      expect(input.height).toBeGreaterThanOrEqual(43.5);
      expect(send.height).toBeGreaterThanOrEqual(43.5);
      expect(Math.abs(input.y - send.y)).toBeLessThan(1);
    });
  });
}

test.describe("virtual keyboard", () => {
  // US-18 AC1. Red when: the bar with its tray, in the half of a phone the keyboard leaves
  // (360x320 of 640), is taller than the space or pushes Gửi out of it.
  for (const state of ["done", "unclear", "error-unsure", "long"]) {
    test(`${state}: the bar and its tray fit above a 320 px keyboard`, async ({ page }) => {
      await open(page, 360, state, 320);
      const form = await box(page.locator("form[data-command-bar]"));
      const send = await box(page.getByRole("button", { name: "Gửi" }));
      expect(send.y + send.height).toBeLessThanOrEqual(320);
      // The worst case (two pasted paragraphs and three long names) may take 60% of a 640 px phone, never more.
      expect(form.height).toBeLessThanOrEqual(state === "long" ? 384 : 320 - 16);
    });
  }
});

test.describe("keyboard only", () => {
  // US-18 AC1, AC5. Red when: a command cannot be sent, undone or undone again without a pointer.
  test("type, Enter, Tab to Hoàn tác, Enter", async ({ page }) => {
    await open(page, 1440, "idle");
    await page.getByLabel("Gõ một lệnh để sửa").focus();
    await page.keyboard.type("mục 3.4 kết thúc ở trang 80");
    await page.keyboard.press("Enter");
    await expect(page.getByText("Đã làm:")).toBeVisible();
    await expect(page.getByLabel("Gõ một lệnh để sửa")).toHaveValue("");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Hoàn tác" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByText("Đã hoàn tác:")).toBeVisible();
    await expect(page.getByLabel("Gõ một lệnh để sửa")).toBeFocused();
  });

  test("a refused command keeps its words and focus", async ({ page }) => {
    await open(page, 390, "idle");
    await page.getByLabel("Gõ một lệnh để sửa").focus();
    await page.keyboard.type("xóa môn này");
    await page.keyboard.press("Enter");
    await expect(page.getByText("Thao tác này không làm bằng lệnh.")).toBeVisible();
    await expect(page.getByLabel("Gõ một lệnh để sửa")).toHaveValue("xóa môn này");
    await expect(page.getByLabel("Gõ một lệnh để sửa")).toBeFocused();
  });
});
