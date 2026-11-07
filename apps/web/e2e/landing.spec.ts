// LANDING-V61-PORT: the public landing at "/". Anonymous visitors see it and can go on to register / login;
// every other page still sends them to /login. A signed-in cookie leaving "/" is covered by
// tests/landing-route.test.tsx and tests/proxy.test.ts (the __Host- cookie cannot be set over http here).
import { expect, test } from "@playwright/test";

test("anonymous / renders the landing with the approved words and both ways in", async ({ page }) => {
  expect((await page.goto("/"))?.status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/Hôm nay ôn gì,\s*đã có tôi lo!/);
  await expect(page.getByText("Trợ lí học tập tiên tiến. Quản lí lịch ôn luyện hiệu quả với thuật toán FSRS và đồ thị tri thức.")).toBeVisible();
  await expect(page.locator('a[href="/register"]').first()).toBeVisible();
  await expect(page.locator('a[href="/login"]').first()).toBeVisible();
});

test("main flow: the CTA leads to register, the second way in to login", async ({ page }) => {
  await page.goto("/");
  await page.locator('a[href="/register"]').first().click();
  await expect(page).toHaveURL(/\/register$/);
  await page.goto("/");
  await page.locator('a[href="/login"]').first().click();
  await expect(page).toHaveURL(/\/login$/);
});

for (const width of [390, 1280]) {
  test(`the landing does not scroll sideways at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}

test("reduced motion: demos show their finished state and the pause control is there", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.locator("[data-pause]")).toBeAttached();
  await expect(page.locator("#de-cuong")).toContainText("Hiệu ứng Mpemba");
});

test("anonymous /today still goes to /login", async ({ page }) => {
  await page.goto("/today");
  await expect(page).toHaveURL(/\/login$/);
});
