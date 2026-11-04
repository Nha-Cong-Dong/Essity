// T7.12a (design decisions C1-C19): the study session's busiest states at four widths on
// /design-preview/session, and the keyboard paths (the @ list). CARDS-V3: no draft review any more. Geometry only, as
// in today.spec.ts: nothing spills, nothing overlaps, the page never scrolls sideways.
import { expect, type Locator, type Page, test } from "@playwright/test";

import { settled } from "./ready";

const PAGE = "/design-preview/session";
const WIDTHS = [320, 390, 768, 1440];
const STATES = [
  "Trống",
  "Có file",
  "Phạm vi bị từ chối",
  "Đang đọc",
  "Hết lượt AI",
  "Không đọc được",
  "Đã thêm thẻ",
  "Chưa có thẻ",
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

async function open(page: Page, width: number, state?: string, longName = true) {
  await page.setViewportSize({ width, height: 900 });
  expect((await page.goto(PAGE))?.status()).toBe(200);
  await settled(page);
  if (longName) await page.getByLabel("Tên môn dài").check();
  if (state) await page.getByRole("button", { name: state, exact: true }).click();
}

for (const width of WIDTHS) {
  test.describe(`@${width}px`, () => {
    // US-02 AC1-AC15 layout (all states). Red when: a long subject name, a long file name or a long card title pushes the page wider
    // than the screen, in any of the states.
    for (const state of STATES) {
      test(`${state}: the page does not scroll sideways`, async ({ page }) => {
        await open(page, width, state);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      });
    }

    // US-02 AC14 (Học tiếp / Dừng). Red when: the result's link falls outside the column, or the two
    // buttons differ in size (they are equals: no primary, nothing pushes the learner).
    test("result: the link stays in the column; the two buttons are equals", async ({ page }) => {
      await open(page, width, "Đã thêm thẻ");
      const main = page.locator("main");
      const more = page.getByRole("button", { name: "Học tiếp" });
      const stop = page.getByRole("main").getByRole("link", { name: "Dừng" });
      await expect(more).toBeVisible();
      expect(inside(await box(more), await box(main))).toBe(true);
      const [a, b] = [await box(more), await box(stop)];
      expect(Math.abs(a.height - b.height)).toBeLessThan(1);
      expect(Math.abs(a.width - b.width)).toBeLessThan(width < 481 ? 1 : 80);
    });

    // US-02 AC2 (files). Red when: a file row's state text runs over its remove button.
    test("files: every row stays inside the column", async ({ page }) => {
      await open(page, width, "Có file");
      const main = page.locator("main");
      for (const item of await page.getByRole("list", { name: "File đã chọn" }).getByRole("listitem").all()) {
        expect(inside(await box(item), await box(main))).toBe(true);
      }
    });
  });
}

test.describe("keyboard", () => {
  test.beforeEach(async ({ page }) => open(page, 390, undefined, false));

  // US-02 AC2, AC3 (the @ list). Red when: @ no longer opens the list, ↓ + Enter does not choose, or the chosen document is not
  // shown as a chip (US-02 AC2: a reference is exact, never guessed).
  test("@ opens the documents, arrows and Enter choose one, Esc closes", async ({ page }) => {
    const field = page.getByRole("combobox");
    await field.click();
    await field.pressSequentially("học @sl");
    await expect(page.getByRole("option", { name: /slide c3/ })).toBeVisible();
    await field.press("Escape");
    await expect(page.getByRole("listbox")).toHaveCount(0);
    await field.press("Backspace");
    await field.pressSequentially("l");
    await field.press("ArrowDown");
    await field.press("Enter");
    await expect(field).toHaveValue("học @slide c3 ");
    await expect(page.getByRole("list", { name: "Tài liệu đã chọn" }).getByText("slide c3")).toBeVisible();
  });

  // US-02 AC2 (menu rỗng, DESIGN §6.7). Red when: nothing matches and the user is not told, or Tab is trapped by the menu.
  test("no match says so; Tab leaves the field", async ({ page }) => {
    const field = page.getByRole("combobox");
    await field.click();
    await field.pressSequentially("@zzzz");
    await expect(page.getByRole("listbox").getByText("Không có tài liệu tên này trong kho.")).toBeVisible();
    await field.press("Tab");
    await expect(field).not.toBeFocused();
  });

  // US-02 AC1, AC14 (Học tiếp / Dừng). Red when: the main flow no longer runs from a sentence to "Học tiếp hay dừng?".
  test("main flow: Gửi, cards in the Kho, Học tiếp hay dừng?", async ({ page }) => {
    await page.getByRole("combobox").fill("Hôm nay học cửa sổ trượt.");
    await page.getByRole("button", { name: "Gửi" }).click();
    await expect(page.getByText("Đang đọc bài nộp…")).toBeVisible();
    await expect(page.getByText("Đã thêm 6 thẻ vào Kho.").first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("heading", { name: "Học tiếp hay dừng?" })).toBeVisible();
    await page.getByRole("button", { name: "Học tiếp" }).click();
    await expect(page.getByText("Vòng 1: đã thêm 6 thẻ vào Kho")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Bạn đã học gì?" })).toBeFocused();
  });
});
