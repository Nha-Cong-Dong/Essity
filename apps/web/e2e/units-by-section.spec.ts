// T7.12d (US-02b AC14): the subject's cards grouped by outline section, under the study session,
// on the screen the real page builds; web's /api route is answered here (no core-api).
import { expect, type Page, test } from "@playwright/test";

import { settled } from "./ready";

const PAGE = "/design-preview/session-live";
const URL_PATH = "/api/subjects/c3d4e5f6-7a8b-4c9d-8e1f-2a3b4c5d6e7f/units/by-section";

const long = "Một đoạn tóm tắt khá dài để thử xuống dòng ở màn hẹp, không được tràn ngang ".repeat(3);
const card = (id: string, title: string, status: string) => ({ id, title, content: long, kind: "concept", status });
const GROUPS = {
  groups: [
    { section_id: "s1", section_title: "Chương 3: Tầng giao vận và điều khiển luồng", units: [card("a", "Cửa sổ trượt", "canonical")] },
    { section_id: "s2", section_title: "Chương 4", units: [card("b", "Định tuyến", "draft")] },
    { section_id: null, section_title: null, units: [card("c", "Thẻ lẻ", "draft")] },
  ],
};

async function open(page: Page, groups: unknown, width = 390) {
  await page.route("**/api/**", (route) =>
    new URL(route.request().url()).pathname === URL_PATH
      ? route.fulfill({ status: 200, json: groups })
      : route.fulfill({ status: 503, json: { error: "unavailable" } }),
  );
  await page.setViewportSize({ width, height: 900 });
  expect((await page.goto(PAGE))?.status()).toBe(200);
  await settled(page);
}

test.describe("AC14 cards by section", () => {
  // Red when: a section is not a group, or the loose cards are not last under their own heading.
  test("AC14 shows a group per section and the cards in no section last", async ({ page }) => {
    await open(page, GROUPS);
    const heads = page.locator("#by-section-h ~ div h3");
    await expect(heads).toHaveCount(3);
    await expect(heads.nth(0)).toContainText("Chương 3");
    await expect(heads.nth(1)).toContainText("Chương 4");
    await expect(heads.nth(2)).toContainText("Chưa gắn phần");
    await expect(page.getByText("Thẻ lẻ")).toBeVisible();
  });

  // Red when: a subject with no cards still shows the block.
  test("AC14 shows nothing when the subject has no cards", async ({ page }) => {
    await open(page, { groups: [] });
    await expect(page.getByRole("heading", { name: "Bạn đã học gì?" })).toBeVisible();
    await expect(page.locator("#by-section-h")).toHaveCount(0);
  });

  // Red when: at 320 px the block makes the page scroll sideways.
  test("AC14 320 px: the groups do not scroll sideways", async ({ page }) => {
    await open(page, GROUPS, 320);
    await expect(page.locator("#by-section-h")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  });
});
