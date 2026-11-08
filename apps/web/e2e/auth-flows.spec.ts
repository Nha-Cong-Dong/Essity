// QA-NIGHT-A: every account/auth flow end to end against the running stack (web + core-api +
// Mailpit). Set E2E_STACK_URL (e.g. http://localhost:3000); without it, or without Mailpit, the
// tests skip. Each test registers its own throwaway account; no existing account is touched.
import { expect, type Page, test } from "@playwright/test";

import { settled } from "./ready";

const MAILPIT = (process.env.MAILPIT_URL ?? "http://localhost:8025").replace(/\/$/, "");

async function mailpitUp(): Promise<boolean> {
  try {
    return (await fetch(`${MAILPIT}/api/v1/info`, { signal: AbortSignal.timeout(2000) })).ok;
  } catch {
    return false;
  }
}

let counter = 0;
function account(tag: string) {
  const stamp = `${Date.now()}`.slice(-9) + counter++;
  return {
    // Usernames are capped at 20 characters: tag (2) + 10 digits.
    username: `${tag}${stamp}`,
    email: `e2e.${tag}.${stamp}@example.com`,
    password: `e2e-${stamp}-pw`,
  };
}
type Account = ReturnType<typeof account>;

async function mailLink(email: string, path: "verify-email" | "reset-password", origin: string, after = 0) {
  const deadline = Date.now() + 15_000;
  const re = new RegExp(`https?://[^\\s"'<>]+/${path}\\?token=[^\\s"'<>]+`);
  while (Date.now() < deadline) {
    const found = await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:${email}`)}`);
    const messages = ((await found.json()) as { messages?: { ID: string; Created: string }[] }).messages ?? [];
    for (const m of messages.filter((x) => Date.parse(x.Created) > after)) {
      const mail = (await (await fetch(`${MAILPIT}/api/v1/message/${m.ID}`)).json()) as { Text: string; HTML: string };
      const match = re.exec(`${mail.Text}\n${mail.HTML}`);
      if (match) {
        const url = new URL(match[0].replace(/&amp;/g, "&"));
        return `${origin}${url.pathname}${url.search}`;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`no ${path} mail for ${email} within 15 s`);
}

// The landing page draws inline SVG that React never owns, so `settled` (every node hydrated) does
// not fit it: wait for <main> itself to be hydrated.
async function mainHydrated(page: Page) {
  await page.waitForFunction(() => {
    const main = document.querySelector("main");
    return !!main && Object.keys(main).some((k) => k.startsWith("__reactFiber$"));
  });
}

// core-api sends mail to one address at most once a minute (EMAIL_COOLDOWN, whichever endpoint),
// and answers 429 "Thử lại sau 1 phút" in between: wait it out once, then press again.
async function pressThroughCooldown(page: Page, button: string, done: () => Promise<unknown>) {
  await page.getByRole("button", { name: button }).click();
  const limited = page.getByText(/Thử lại sau \d+ phút/);
  const first = await Promise.race([done().then(() => "done"), limited.waitFor().then(() => "limited")]).catch(() => "limited");
  if (first === "done") return;
  await page.waitForTimeout(62_000);
  await page.getByRole("button", { name: button }).click();
  await done();
}

async function fillRegister(page: Page, a: Account) {
  await page.goto("/register");
  await settled(page);
  await page.getByLabel("Tên đăng nhập").fill(a.username);
  await page.getByLabel("Email").fill(a.email);
  await page.locator("#password").fill(a.password);
}

async function signIn(page: Page, identifier: string, password: string) {
  await page.goto("/login");
  await settled(page);
  await page.getByLabel("Tên đăng nhập hoặc email").fill(identifier);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
}

async function verified(page: Page, a: Account, origin: string) {
  await fillRegister(page, a);
  await page.getByRole("button", { name: "Tạo tài khoản" }).click();
  await page.waitForURL("**/check-email");
  const link = await mailLink(a.email, "verify-email", origin);
  await page.context().clearCookies();
  await page.goto(link);
  await expect(page.getByText("Đã xác minh email.")).toBeVisible();
}

// core-api allows 10 sign-ups an hour per IP (REGISTER_PER_IP), so the registering tests below use
// 6 in all (the duplicate checks count too): leave room before a second run within the hour.
test.beforeEach(async () => {
  test.skip(!process.env.E2E_STACK_URL, "E2E_STACK_URL not set: no core-api behind the web app");
  test.skip(!(await mailpitUp()), `Mailpit not reachable at ${MAILPIT}`);
});

test("pages raise no console errors or failed requests (landing, login, register, forgot)", async ({ page }) => {
  const problems: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") problems.push(`console: ${m.text()}`);
  });
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  page.on("response", (r) => {
    if (r.status() >= 400) problems.push(`${r.status()} ${r.url()}`);
  });
  for (const path of ["/", "/login", "/register", "/forgot-password"]) {
    await page.goto(path);
    await mainHydrated(page);
  }
  expect(problems).toEqual([]);
});

test("landing links to register and login, and no landing link is dead", async ({ page }) => {
  await page.goto("/");
  await mainHydrated(page);
  const hrefs = await page.locator("a[href]").evaluateAll((as) => as.map((a) => a.getAttribute("href")));
  expect(hrefs.some((h) => h?.startsWith("/register"))).toBe(true);
  expect(hrefs.some((h) => h?.startsWith("/login"))).toBe(true);
  const local = [...new Set(hrefs.filter((h): h is string => !!h && h.startsWith("/") && !h.startsWith("//")))];
  for (const h of local) {
    const status = (await page.request.get(h)).status();
    expect(status, `landing link ${h}`).toBeLessThan(400);
  }
});

test("register: client validation on bad email, short password, long username", async ({ page }) => {
  const a = account("va");
  await page.goto("/register");
  await settled(page);
  await page.getByLabel("Tên đăng nhập").fill(a.username);
  await page.getByLabel("Email").fill("not-an-email");
  await page.locator("#password").fill("short");
  await page.getByLabel("Họ và tên (không bắt buộc)").click(); // blur the password
  await expect(page.locator("#email-error")).toBeVisible();
  await expect(page.locator("#password-error")).toBeVisible();
  await page.getByRole("button", { name: "Tạo tài khoản" }).click();
  await expect(page).toHaveURL(/\/register$/);
  await page.getByLabel("Tên đăng nhập").fill("a".repeat(30));
  expect(await page.getByLabel("Tên đăng nhập").inputValue()).toHaveLength(20);
});

test("verify: no token or a garbage token is expired, not a crash", async ({ page }) => {
  await page.goto("/verify-email");
  await expect(page.getByText("Link này đã hết hạn hoặc đã được dùng.")).toBeVisible();
  await page.goto("/verify-email?token=garbage");
  await expect(page.getByText("Link này đã hết hạn hoặc đã được dùng.")).toBeVisible();
  await page.goto("/reset-password?token=garbage");
  await settled(page);
  await page.locator("#password").fill("long-enough-pw-1");
  await page.getByRole("button", { name: "Lưu mật khẩu" }).click();
  await expect(page.getByText("Link này đã hết hạn hoặc đã được dùng.")).toBeVisible();
});

test("signed out: protected pages go to /login, APIs answer 401", async ({ page }) => {
  for (const path of ["/today", "/stats", "/review", "/subjects/new", "/kho-kien-thuc", "/graph"]) {
    await page.goto(path);
    await expect(page, path).toHaveURL(/\/login$/);
  }
  expect((await page.request.get("/api/export")).status()).toBe(401);
});

test("unverified account: check-email, sign-in, duplicates, wrong email", async ({ page }) => {
  test.setTimeout(120_000); // waits out the 1-minute per-address mail cooldown
  const a = account("un");
  await fillRegister(page, a);
  await page.getByRole("button", { name: "Tạo tài khoản" }).click();
  await page.waitForURL("**/check-email");
  await expect(page.getByRole("button", { name: /Gửi lại \(\d+:\d\d\)/ })).toBeDisabled();
  await page.context().clearCookies();

  // Duplicate username is said; a duplicate email moves on exactly as a new one does (AC5).
  const other = account("uo");
  await fillRegister(page, { ...other, username: a.username });
  await page.getByRole("button", { name: "Tạo tài khoản" }).click();
  await expect(page.locator("#username-error")).toBeVisible();
  await expect(page).toHaveURL(/\/register$/);
  await fillRegister(page, { ...other, email: a.email });
  await pressThroughCooldown(page, "Tạo tài khoản", () => page.waitForURL("**/check-email"));
  await page.context().clearCookies();

  await signIn(page, a.username, a.password);
  await page.waitForURL("**/check-email");
  await page.goto("/today");
  await expect(page).toHaveURL(/\/check-email$/);
  await page.getByRole("button", { name: "Đăng xuất" }).click();
  await page.waitForURL("**/register");

  await signIn(page, a.username, "wrong-password-1");
  await expect(page.locator("#login-error")).toBeVisible();
  const wrongText = await page.locator("#login-error").innerText();
  await expect(page).toHaveURL(/\/login$/);
  await signIn(page, `nobody${a.username}`, "wrong-password-1");
  await expect(page.locator("#login-error")).toHaveText(wrongText);
});

test("full life of an account: verify, reuse link, sign in, CSV, sign out, forgot, reset, sign in again", async ({
  page,
  baseURL,
}) => {
  test.setTimeout(180_000);
  const a = account("fl");
  await fillRegister(page, a);
  await page.getByRole("button", { name: "Tạo tài khoản" }).click();
  await page.waitForURL("**/check-email");
  const first = await mailLink(a.email, "verify-email", baseURL!);
  await page.context().clearCookies();
  await page.goto(first);
  await expect(page.getByText("Đã xác minh email.")).toBeVisible();
  await page.goto(first);
  await expect(page.getByText("Link này đã hết hạn hoặc đã được dùng.")).toBeVisible();
  await page.getByRole("button", { name: "Gửi link mới" }).or(page.getByRole("link", { name: "Gửi link mới" })).click();
  await page.waitForURL("**/login");

  await signIn(page, a.email.toUpperCase(), a.password);
  await page.waitForURL("**/subjects/new");
  const csv = await page.request.get("/api/export");
  expect(csv.status()).toBe(200);
  expect(csv.headers()["content-type"]).toContain("text/csv");

  await page.goto("/login");
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));

  await page.goto("/subjects/new");
  await settled(page);
  await page.getByRole("button", { name: "Tài khoản", exact: true }).click();
  await page.getByRole("menuitem", { name: "Đăng xuất" }).click();
  await page.waitForURL((u) => u.pathname === "/" || u.pathname === "/login");
  await page.goto("/today");
  await expect(page).toHaveURL(/\/login$/);
  expect((await page.request.get("/api/export")).status()).toBe(401);

  await page.goto("/forgot-password");
  await settled(page);
  await page.getByLabel("Email").fill(`nobody.${a.email}`);
  await page.getByRole("button", { name: "Gửi link đặt lại" }).click();
  await expect(page.getByText("Đã gửi link tới")).toBeVisible();

  const since = Date.now() - 2000;
  await page.goto("/forgot-password");
  await settled(page);
  await page.getByLabel("Email").fill(a.email);
  await pressThroughCooldown(page, "Gửi link đặt lại", () => page.getByText("Đã gửi link tới").waitFor());
  const link = await mailLink(a.email, "reset-password", baseURL!, since);

  await page.goto(link);
  await settled(page);
  await page.locator("#password").fill("short");
  await page.getByRole("button", { name: "Lưu mật khẩu" }).click();
  await expect(page.locator("#password-error")).toBeVisible();
  const next = `${a.password}-new`;
  await page.locator("#password").fill(next);
  await page.getByRole("button", { name: "Lưu mật khẩu" }).click();
  await expect(page.getByText("Đã đặt mật khẩu mới.")).toBeVisible();

  // The token is only checked on submit (reset-password.tsx): a used link fails when sent.
  await page.goto(link);
  await settled(page);
  await page.locator("#password").fill(`${next}-again`);
  await page.getByRole("button", { name: "Lưu mật khẩu" }).click();
  await expect(page.getByText("Link này đã hết hạn hoặc đã được dùng.")).toBeVisible();

  await signIn(page, a.username, a.password);
  await expect(page.locator("#login-error")).toBeVisible();
  await signIn(page, a.username, next);
  await page.waitForURL("**/subjects/new");
});

test("a dead session cookie does not loop and the user can sign in again", async ({ page, context, baseURL }) => {
  const a = account("ds");
  await verified(page, a, baseURL!);
  await signIn(page, a.username, a.password);
  await page.waitForURL("**/subjects/new");
  const session = (await context.cookies()).find((c) => c.httpOnly);
  expect(session).toBeDefined();
  await context.clearCookies();
  await context.addCookies([{ ...session!, value: `dead-token-${"x".repeat(30)}` }]);
  const response = await page.goto("/today");
  expect(response?.status()).toBeLessThan(400);
  await expect(page).toHaveURL(/\/login$/);
  expect((await page.request.get("/api/export")).status()).toBe(401);
  await signIn(page, a.username, a.password);
  await page.waitForURL("**/subjects/new");
});

test("reset: a session open before the reset ends with it", async ({ page, browser, baseURL }) => {
  test.setTimeout(150_000);
  const a = account("rs");
  await verified(page, a, baseURL!);
  await signIn(page, a.username, a.password);
  await page.waitForURL("**/subjects/new");

  const other = await browser.newContext({ baseURL });
  const p2 = await other.newPage();
  const since = Date.now() - 2000;
  await p2.goto("/forgot-password");
  await settled(p2);
  await p2.getByLabel("Email").fill(a.email);
  await pressThroughCooldown(p2, "Gửi link đặt lại", () => p2.getByText("Đã gửi link tới").waitFor());
  await p2.goto(await mailLink(a.email, "reset-password", baseURL!, since));
  await settled(p2);
  await p2.locator("#password").fill(`${a.password}-x`);
  await p2.getByRole("button", { name: "Lưu mật khẩu" }).click();
  await expect(p2.getByText("Đã đặt mật khẩu mới.")).toBeVisible();
  await other.close();

  await page.goto("/today");
  await expect(page).toHaveURL(/\/login$/);
  expect((await page.request.get("/api/export")).status()).toBe(401);
});
