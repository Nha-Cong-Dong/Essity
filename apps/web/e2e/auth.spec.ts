// T1.24 (US-12 AC1, AC5): the account screens against the approved mockup
// docs/design/screens-html/auth-v2. Geometry only, never screenshots compared (fonts differ);
// nothing calls core-api here, so only what renders without a session is checked.
import { expect, test } from "@playwright/test";

import { settled } from "./ready";

const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };

for (const path of ["/login", "/register", "/forgot-password"]) {
  test(`AC1: ${path} at 1440 is one card, at most 420px, centred`, async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await page.goto(path);
    await settled(page);
    const card = await page.locator("main > div").boundingBox();
    expect(card).not.toBeNull();
    expect(card!.width).toBeLessThanOrEqual(420.5);
    expect(Math.abs(card!.x + card!.width / 2 - DESKTOP.width / 2)).toBeLessThan(2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });

  test(`AC1: ${path} at 390 is the logo, then the card filling the width`, async ({ page }) => {
    await page.setViewportSize(PHONE);
    await page.goto(path);
    await settled(page);
    await expect(page.locator('[data-auth="top"] a')).toHaveText("Essity");
    const card = await page.locator("main > div").boundingBox();
    expect(card!.width).toBeGreaterThan(PHONE.width - 40);
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

test("D7: sign-up with Họ và tên sends display_name and moves on to /check-email", async ({ page }) => {
  await page.setViewportSize(PHONE);
  let sent: Record<string, unknown> | undefined;
  await page.route("**/api/auth/username-available**", (route) =>
    route.fulfill({ json: { available: true, reason: null } }),
  );
  await page.route("**/api/auth/register", async (route) => {
    sent = route.request().postDataJSON();
    await route.fulfill({ json: { next: "/check-email" } });
  });
  await page.goto("/register");
  await settled(page);
  await page.getByLabel("Tên đăng nhập").fill("an.nguyen");
  await page.getByLabel("Email").fill("an@gmail.com");
  await page.locator("#password").fill("matkhau-dai-123");
  await page.getByLabel("Họ và tên (không bắt buộc)").fill(" Nguyễn Văn An ");
  await Promise.all([
    page.waitForRequest("**/api/auth/register"),
    page.getByRole("button", { name: "Tạo tài khoản" }).click(),
  ]);
  expect(sent).toEqual({
    username: "an.nguyen",
    email: "an@gmail.com",
    password: "matkhau-dai-123",
    display_name: "Nguyễn Văn An",
  });
});
