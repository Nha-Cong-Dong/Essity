// T0.15: the public landing at "/". Anonymous visitors see it; every other page still sends them
// to /login; a signed-in cookie leaves "/" for the app. The demo is client-side only.
import { expect, type Page, test } from "@playwright/test";

const COOKIE = "__Host-essity_session";

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

test("anonymous /today still goes to /login", async ({ page }) => {
  await page.goto("/today");
  await expect(page).toHaveURL(/\/login$/);
});

test("with a session cookie / is not the landing: the app takes over", async ({ page, context }) => {
  await context.addCookies([{ name: COOKIE, value: "not-a-real-session", url: "http://127.0.0.1:3100", secure: true }]);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Tối nay ôn gì/ })).toHaveCount(0);
});
