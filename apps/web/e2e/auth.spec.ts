// T1.24 (US-12 AC1, AC5): the account screens against the approved mockup
// docs/design/screens-html/auth-v2. Geometry only, never screenshots compared (fonts differ);
// nothing calls core-api here, so only what renders without a session is checked.
import { expect, test } from "@playwright/test";

import { settled } from "./ready";

const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };

for (const path of ["/login", "/register", "/forgot-password"]) {
  test(`AC1: ${path} at 1440 is a 5/7 split, poster left, form at most 400px`, async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await page.goto(path);
    await settled(page);
    const poster = await page.locator('[data-auth="poster"]').boundingBox();
    const panel = await page.locator("main > div").boundingBox();
    expect(poster).not.toBeNull();
    expect(panel).not.toBeNull();
    expect(poster!.x).toBe(0);
    expect(Math.abs(poster!.width - (DESKTOP.width * 5) / 12)).toBeLessThan(2);
    expect(panel!.width).toBeLessThanOrEqual(400.5);
    expect(panel!.x).toBeGreaterThanOrEqual(poster!.width);
    // The tilted notebook is a picture: nothing in it can be focused or read as the page.
    await expect(page.locator('[data-auth="poster"] [aria-hidden="true"]').first()).toBeAttached();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });

  test(`AC1: ${path} at 390 is a 72px poster strip with the logo only, then the form`, async ({ page }) => {
    await page.setViewportSize(PHONE);
    await page.goto(path);
    await settled(page);
    const poster = await page.locator('[data-auth="poster"]').boundingBox();
    expect(poster!.height).toBeCloseTo(72, 0);
    expect(poster!.width).toBeCloseTo(PHONE.width, 0);
    await expect(page.locator('[data-auth="poster"] a')).toHaveText("Essity");
    await expect(page.getByText("Tối nay ôn gì")).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}

test("AC5: /login has one identifier field, 'Quên mật khẩu?' under the password, 44px tall, no Google", async ({
  page,
}) => {
  await page.setViewportSize(PHONE);
  await page.goto("/login");
  await settled(page);
  const identifier = page.getByLabel("Tên đăng nhập hoặc email");
  await expect(identifier).toHaveAttribute("autocomplete", "username");
  await expect(identifier).toHaveAttribute("autocapitalize", "none");
  await expect(page.getByLabel("Email", { exact: true })).toHaveCount(0);
  const password = await page.locator("#password").boundingBox();
  const forgot = await page.getByRole("link", { name: "Quên mật khẩu?" }).boundingBox();
  expect(forgot!.y).toBeGreaterThan(password!.y + password!.height - 1);
  expect(forgot!.height).toBeGreaterThanOrEqual(44);
  await expect(page.getByText("Google")).toHaveCount(0);
});

test("AC1: /register has username, email, password, then the optional name last, no phone", async ({ page }) => {
  await page.setViewportSize(PHONE);
  await page.goto("/register");
  await settled(page);
  const names = await page.locator("main input").evaluateAll((inputs) => inputs.map((i) => (i as HTMLInputElement).name));
  expect(names).toEqual(["username", "email", "password", "name"]);
  await expect(page.getByText("Essity gọi bạn bằng tên này")).toBeVisible();
  const field = page.getByLabel("Tên đăng nhập");
  await field.fill("An.Nguyen");
  await expect(field).toHaveValue("an.nguyen");
});
