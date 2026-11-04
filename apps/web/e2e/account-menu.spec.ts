// UI-A: the avatar menu opens inside the window and on top of the rail, so every item can be clicked.
import { expect, test } from "@playwright/test";

for (const [width, height] of [
  [1440, 900],
  [390, 844],
]) {
  test(`account menu: the last item is inside the window and on top @ ${width}x${height}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    expect((await page.goto("/design-preview/subjects"))?.status()).toBe(200);
    await page.evaluate(() => document.fonts.ready);
    await page.getByRole("button", { name: "Tài khoản", exact: true }).click();
    const item = page.getByRole("menuitem", { name: "Đăng xuất" });
    await expect(item).toBeVisible();
    const box = (await item.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width);
    expect(box.y + box.height).toBeLessThanOrEqual(height);
    const onTop = await item.evaluate((el) => {
      const r = el.getBoundingClientRect();
      const hit = document.elementFromPoint(r.x + 20, r.y + r.height / 2);
      return hit !== null && el.closest('[role="menu"]')?.contains(hit) === true;
    });
    expect(onTop).toBe(true);
    await page.keyboard.press("Escape");
    await expect(item).toBeHidden();
    await expect(page.getByRole("button", { name: "Tài khoản", exact: true })).toBeFocused();
  });
}
