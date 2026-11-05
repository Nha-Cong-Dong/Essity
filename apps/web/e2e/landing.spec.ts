// T0.15: the public landing at "/". Anonymous visitors see it; every other page still sends them
// to /login; the demo is client-side only. A signed-in cookie leaving "/" is covered by
// tests/landing-route.test.tsx and tests/proxy.test.ts (the __Host- cookie cannot be set over http here).
import { expect, type Page, test } from "@playwright/test";

async function hydrated(page: Page) {
  await page.waitForFunction(() => {
    const button = document.querySelector("button[aria-pressed]");
    return button !== null && Object.keys(button).some((k) => k.startsWith("__reactFiber$"));
  });
}

test("anonymous / renders the landing with the approved words and both ways in", async ({ page }) => {
  expect((await page.goto("/"))?.status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/Tối nay ôn gì,\s*đã có app lo/);
  await expect(page.getByText("Trợ lí học tập thông minh. Quản lí lịch ôn tập hiệu quả với thuật toán FSRS.")).toBeVisible();
  await expect(page.locator('a[href="/register"]').first()).toBeVisible();
  await expect(page.locator('a[href="/login"]').first()).toBeVisible();
});

for (const width of [390, 1280]) {
  test(`the landing does not scroll sideways at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}

test("the grading demo answers from the page itself: no request to the API", async ({ page }) => {
  const calls: string[] = [];
  page.on("request", (r) => {
    if (new URL(r.url()).pathname.startsWith("/api/")) calls.push(r.url());
  });
  await page.goto("/");
  await hydrated(page);
  await page.getByRole("button", { name: "Đủ ý" }).click();
  await expect(page.getByRole("button", { name: "Đủ ý" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("đủ cả hai ý")).toBeVisible();
  await page.getByRole("button", { name: "Không nhớ" }).click();
  await expect(page.getByText("đáp án ở trang nguồn")).toBeVisible();
  expect(calls).toEqual([]);
});

test("v2 sections come in order, the FAQ has five questions and the new figures carry text labels", async ({ page }) => {
  await page.goto("/");
  const ids = await page.evaluate(() => [...document.querySelectorAll("main section[id]")].map((s) => s.id));
  expect(ids.indexOf("hoc-gi-tiep")).toBeGreaterThan(ids.indexOf("cach-hoat-dong"));
  expect(ids.indexOf("luyen-dang-de")).toBeGreaterThan(ids.indexOf("hoc-gi-tiep"));
  expect(ids.indexOf("hoi-dap")).toBeGreaterThan(ids.indexOf("luyen-dang-de"));
  await expect(page.locator("#hoi-dap dt")).toHaveCount(5);
  await expect(page.getByText("Sửa nhanh thế nào?")).toBeVisible();
  await expect(page.locator("#hoc-gi-tiep")).toContainText("✓ Đã học");
  await expect(page.locator("#hoc-gi-tiep")).toContainText("→ Tiếp theo");
  await expect(page.locator("#luyen-dang-de")).toContainText("→ Gợi ý: liên quan tới Định tuyến");
});

test("anonymous /today still goes to /login", async ({ page }) => {
  await page.goto("/today");
  await expect(page).toHaveURL(/\/login$/);
});
