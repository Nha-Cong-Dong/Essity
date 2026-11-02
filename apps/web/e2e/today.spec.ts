// T2.14 (ADR-0025): /today's busiest state at four widths, on /design-preview/today-v1 (the screen /today draws now). Geometry
// only, as in layout.spec.ts: nothing spills, nothing overlaps, the page never scrolls sideways.
import { expect, type Locator, type Page, test } from "@playwright/test";

import { settled } from "./ready";

const PAGE = "/design-preview/today-v1";
const WIDTHS = [320, 390, 768, 1440];

type Box = { x: number; y: number; width: number; height: number };

async function box(locator: Locator): Promise<Box> {
  const found = await locator.boundingBox();
  if (found === null) throw new Error("no box");
  return found;
}

const inside = (inner: Box, outer: Box) =>
  inner.x >= outer.x - 0.5 &&
  inner.y >= outer.y - 0.5 &&
  inner.x + inner.width <= outer.x + outer.width + 0.5 &&
  inner.y + inner.height <= outer.y + outer.height + 0.5;

const overlap = (a: Box, b: Box) =>
  a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;

async function open(page: Page, width: number) {
  await page.setViewportSize({ width, height: 900 });
  expect((await page.goto(PAGE))?.status()).toBe(200);
  await settled(page);
}

for (const width of WIDTHS) {
  test.describe(`@${width}px`, () => {
    test.beforeEach(async ({ page }) => open(page, width));

    // Red when: a tile or the long subject name pushes the page wider than the screen.
    test("the page does not scroll sideways", async ({ page }) => {
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });

    // Red when: "Bắt đầu" falls outside the pink tile it belongs to.
    test("Bắt đầu sits inside the session tile", async ({ page }) => {
      const tile = page.locator('[data-surface="hong"]');
      expect(inside(await box(page.getByRole("button", { name: "Bắt đầu" })), await box(tile))).toBe(true);
    });

    // Red when: the backlog sentence runs into "Ôn thêm" instead of wrapping beside or above it.
    test("the backlog sentence and Ôn thêm do not overlap", async ({ page }) => {
      const sentence = page.getByText(/^Để kịp thi/);
      const more = page.getByRole("button", { name: "Ôn thêm" });
      expect(overlap(await box(sentence), await box(more))).toBe(false);
    });

    // Red when: a long subject name spills out of the subjects tile.
    test("subject names stay inside their tile", async ({ page }) => {
      const tile = page.getByRole("heading", { name: "Môn đang ôn" }).locator("xpath=..");
      for (const item of await tile.getByRole("listitem").all()) {
        expect(inside(await box(item), await box(tile))).toBe(true);
      }
    });
  });
}

// T7.13 (US-03, US-15 AC6): the main flow. Hôm nay (v2) offers "Vào buổi học"; the subject screen's
// "Gợi ý cho hôm nay" asks the suggestion route (answered here, no core-api), shows the section,
// and "Vào buổi học" goes to the study route (guarded: with no session it lands on /login). A failing answer never stays on "Đang tính…".
const SUBJECT = "0b8f1d2e-0000-4000-8000-000000000001";
const SUGGESTION = {
  today: "2026-11-02",
  suggestion: {
    subject_id: SUBJECT,
    subject_name: "Mạng máy tính",
    kind: "next_leaf",
    section_id: "5f0c0000-0000-4000-8000-000000000001",
    section_title: "3.2 TCP flow control",
    partial: false,
    remaining: null,
    unit: "mục",
    reason: "Môn thi sau 20 ngày, còn 12 mục.",
    pace: { remaining_leaves: 12, remaining_weight: 12, unit: "mục", days_left: 20, text: "còn 12 mục, 20 ngày" },
  },
};

test("US-15 AC6: Hôm nay -> Gợi ý cho hôm nay -> Vào buổi học", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto("/design-preview/today?state=learn");
  await settled(page);
  const enter = page.getByRole("button", { name: /^Vào buổi học · Mạng máy tính/ });
  await expect(enter).toHaveAttribute("href", `/subjects/${SUBJECT}/sessions/new`);

  let asked = 0;
  await page.route(`**/api/subjects/${SUBJECT}/suggestion`, (route) => {
    asked += 1;
    return route.fulfill({ json: SUGGESTION });
  });
  await page.goto("/design-preview/subject-live?state=not-suggested");
  await settled(page);
  await page.getByRole("button", { name: "Gợi ý cho hôm nay" }).click();
  await expect(page.getByText("Hôm nay nên học: mục 3.2")).toBeVisible();
  await expect(page.getByText("còn 12 mục, 20 ngày")).toBeVisible();
  expect(asked).toBe(1);
  const study = page.getByRole("button", { name: /^Vào buổi học/ });
  await expect(study).toHaveAttribute("href", `/subjects/${SUBJECT}/sessions/new`);
  await study.click();
  await page.waitForURL(/\/login/); // the study route is guarded: no session, so the sign-in page
});

test("US-15 AC6: a failing suggestion route ends in a message, not Đang tính…", async ({ page }) => {
  await page.route(`**/api/subjects/${SUBJECT}/suggestion`, (route) => route.fulfill({ status: 502, json: { error: "unavailable" } }));
  await page.goto("/design-preview/subject-live?state=not-suggested");
  await settled(page);
  await page.getByRole("button", { name: "Gợi ý cho hôm nay" }).click();
  await expect(page.getByText("Chưa tính được gợi ý")).toBeVisible();
  await expect(page.locator("main [role=alert]")).toContainText("Chưa tính được gợi ý");
  await expect(page.getByRole("button", { name: "Gợi ý cho hôm nay" })).toBeVisible();
  await expect(page.getByText("Đang tính…")).toHaveCount(0);
});

test("US-03 AC7: the preview's Bắt đầu never calls the API", async ({ page }) => {
  const calls: string[] = [];
  await page.route("**/api/**", (route) => {
    calls.push(route.request().url());
    return route.fulfill({ status: 503, json: {} });
  });
  await page.goto("/design-preview/today?state=review");
  await settled(page);
  await page.getByRole("button", { name: "Bắt đầu" }).click();
  expect(calls).toEqual([]);
});
