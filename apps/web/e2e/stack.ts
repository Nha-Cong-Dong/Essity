// QA-NIGHT-B: helpers for specs that hit the REAL running stack (E2E_STACK_URL), no mocked API.
import { expect, type Page } from "@playwright/test";

import { settled } from "./ready";

export const MAILPIT = (process.env.MAILPIT_URL ?? "http://localhost:8025").replace(/\/$/, "");

export async function mailpitUp(): Promise<boolean> {
  try {
    return (await fetch(`${MAILPIT}/api/v1/info`, { signal: AbortSignal.timeout(2000) })).ok;
  } catch {
    return false;
  }
}

export async function verifyLink(email: string, origin: string): Promise<string> {
  const deadline = Date.now() + 15_000;
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
  throw new Error(`no verification mail for ${email}`);
}

export type Account = { username: string; email: string; password: string };

export function newAccount(tag: string): Account {
  const stamp = Date.now().toString().slice(-9);
  return { username: `${tag}${stamp}`, email: `e2e.${tag}.${stamp}@example.com`, password: `e2e-${stamp}-pw` };
}

/** Register, open the mail link, sign in. Ends on the signed-in landing page. */
export async function registerAndSignIn(page: Page, account: Account, origin: string): Promise<void> {
  await page.goto("/register");
  await settled(page);
  await page.getByLabel("Tên đăng nhập").fill(account.username);
  await page.getByLabel("Email").fill(account.email);
  await page.locator("#password").fill(account.password);
  await page.getByRole("button", { name: "Tạo tài khoản" }).click();
  await page.waitForURL("**/check-email");
  const link = await verifyLink(account.email, origin);
  await page.goto(link);
  await expect(page.getByText("Đã xác minh email.")).toBeVisible();
  await page.goto("/login");
  await settled(page);
  await page.getByLabel("Tên đăng nhập hoặc email").fill(account.username);
  await page.locator("#password").fill(account.password);
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await page.waitForURL("**/subjects/new");
}

/** Collects console errors and failed requests (4xx/5xx on our own origin) for a page. */
export function watch(page: Page) {
  const problems: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") problems.push(`console: ${m.text().slice(0, 300)}`);
  });
  page.on("pageerror", (e) => problems.push(`pageerror: ${String(e).slice(0, 300)}`));
  page.on("response", (r) => {
    if (r.status() >= 400 && r.url().startsWith(process.env.E2E_STACK_URL ?? "http://localhost:3000")) {
      problems.push(`${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`);
    }
  });
  return problems;
}
