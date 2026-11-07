// EMAIL-E2E: the real verification mail, read from Mailpit. Registers a new account, opens the link
// from the mail, opens it again (used), then signs in. Needs the full stack (core-api, Mailpit) behind
// the web app: set E2E_STACK_URL to its origin (e.g. http://localhost:3000). Without it, or when
// Mailpit is down, the test skips (CI runs the standalone server with no core-api).
import { expect, test } from "@playwright/test";

import { settled } from "./ready";

const MAILPIT = (process.env.MAILPIT_URL ?? "http://localhost:8025").replace(/\/$/, "");

async function mailpitUp(): Promise<boolean> {
  try {
    return (await fetch(`${MAILPIT}/api/v1/info`, { signal: AbortSignal.timeout(2000) })).ok;
  } catch {
    return false;
  }
}

async function verifyLink(email: string, origin: string): Promise<string> {
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    const found = await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:${email}`)}`);
    const messages = ((await found.json()) as { messages?: { ID: string }[] }).messages ?? [];
    if (messages.length > 0) {
      const mail = (await (await fetch(`${MAILPIT}/api/v1/message/${messages[0].ID}`)).json()) as {
        Text: string;
        HTML: string;
      };
      const match = /https?:\/\/[^\s"'<>]+\/verify-email\?token=[^\s"'<>]+/.exec(`${mail.Text}\n${mail.HTML}`);
      if (match) {
        const url = new URL(match[0].replace(/&amp;/g, "&"));
        return `${origin}${url.pathname}${url.search}`;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`no verification mail for ${email} within 10 s`);
}

test("verification mail: register, open the link, open it again, sign in", async ({ page, baseURL }) => {
  test.skip(!process.env.E2E_STACK_URL, "E2E_STACK_URL not set: no core-api behind the web app");
  test.skip(!(await mailpitUp()), `Mailpit not reachable at ${MAILPIT}`);
  const stamp = Date.now();
  // Usernames are capped at 20 characters: "em" + 13 digits of Date.now() is 15.
  const username = `em${stamp}`;
  const email = `e2e.mail.${stamp}@example.com`;
  const password = `e2e-${stamp}-pw`;

  await page.goto("/register");
  await settled(page);
  await page.getByLabel("Tên đăng nhập").fill(username);
  await page.getByLabel("Email").fill(email);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "Tạo tài khoản" }).click();
  await page.waitForURL("**/check-email");

  const link = await verifyLink(email, baseURL!);

  await page.context().clearCookies();
  await page.goto(link);
  await expect(page.getByText("Đã xác minh email.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Đăng nhập" })).toBeVisible();

  await page.goto(link);
  await expect(page.getByText("Link này đã hết hạn hoặc đã được dùng.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Gửi link mới" })).toBeVisible();

  await page.goto("/login");
  await settled(page);
  await page.getByLabel("Tên đăng nhập hoặc email").fill(username);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await page.waitForURL("**/subjects/new");
});
