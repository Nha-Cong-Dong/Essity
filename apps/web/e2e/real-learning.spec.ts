// QA-NIGHT-B: the learning flow end to end on the REAL stack (web + core-api + ai-service + storage +
// Mailpit), no mocked API. One fresh account is built in the first test and reused by the others (serial),
// so the real AI is called a handful of times in total: one syllabus, one session grading.
// Needs E2E_STACK_URL (the public origin web accepts POSTs from) and Mailpit; skips without them.
import path from "node:path";

import { type BrowserContext, expect, type Page, test } from "@playwright/test";

import { settled } from "./ready";
import { type Account, mailpitUp, newAccount, registerAndSignIn, watch } from "./stack";

const PDF = path.join(__dirname, "fixtures", "biology.pdf");
const account: Account = newAccount("ql");
let subjectId = "";
let context: BrowserContext;
let page: Page;
let problems: string[] = [];

test.beforeAll(async ({ browser }) => {
  if (!process.env.E2E_STACK_URL || !(await mailpitUp())) return;
  context = await browser.newContext({ baseURL: process.env.E2E_STACK_URL });
  page = await context.newPage();
  problems = watch(page);
});
test.afterAll(async () => {
  await context?.close();
});
test.beforeEach(() => {
  test.skip(!process.env.E2E_STACK_URL, "E2E_STACK_URL not set: no stack behind the web app");
});

function noProblems(allowed: RegExp[] = []) {
  const real = problems.filter((p) => !allowed.some((a) => a.test(p)));
  problems.length = 0;
  expect(real, "console errors / 4xx-5xx responses").toEqual([]);
}

// Registration and mail run in their own context, outside the serial chain: when the mail server is
// down this test fails by itself and the rest of the flow still runs with E2E_USER / E2E_PASSWORD
// (an account made earlier by this spec, never an existing person's account).
test.describe("registration", () => {
  test("fresh account: register, verify by mail, sign in lands on 'Tạo môn'", async ({ browser, baseURL }) => {
    test.setTimeout(90_000);
    test.skip(!(await mailpitUp()), "Mailpit not reachable");
    const fresh = await browser.newContext({ baseURL: process.env.E2E_STACK_URL });
    const own = await fresh.newPage();
    await registerAndSignIn(own, account, baseURL ?? process.env.E2E_STACK_URL!);
    await expect(own.getByText("Tạo môn").first()).toBeVisible();
    await fresh.close();
  });
});

test.describe("flow", () => {
  test.describe.configure({ mode: "serial" });
  test("sign in", async () => {
    const user = process.env.E2E_USER ?? account.username;
    const password = process.env.E2E_PASSWORD ?? account.password;
    await page.goto("/login");
    await settled(page);
    await page.getByLabel("Tên đăng nhập hoặc email").fill(user);
    await page.locator("#password").fill(password);
    await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
    await page.waitForURL(/\/(subjects\/new|today)$/);
    noProblems();
  });

  test("create subject: empty and bad input are refused, double submit makes one subject", async () => {
    await page.goto("/subjects/new");
    await settled(page);
    await page.getByRole("button", { name: "Tiếp tục" }).click();
    await expect(page).toHaveURL(/\/subjects\/new$/);
    await expect(page.locator("#subject-name")).toHaveAttribute("aria-invalid", "true");
    await page.locator("#subject-name").fill("Sinh học QA");
    await page.locator("#exam-date").fill("31/02/2026");
    await page.getByRole("button", { name: "Tiếp tục" }).click();
    await expect(page).toHaveURL(/\/subjects\/new$/);
    await expect(page.locator("#exam-date")).toHaveAttribute("aria-invalid", "true");
    await page.locator("#exam-date").fill("01/01/2020");
    await page.getByRole("button", { name: "Tiếp tục" }).click();
    await expect(page.locator("#exam-date")).toHaveAttribute("aria-invalid", "true"); // a past date is refused
    noProblems([/^console: Failed to load resource/, /^4\d\d POST \/api\/subjects/]);

    await page.locator("#exam-date").fill("20/12/2026");
    await page.getByRole("button", { name: "Tiếp tục" }).dblclick();
    await page.waitForURL("**/upload");
    subjectId = /subjects\/([0-9a-f-]{36})\/upload/.exec(page.url())![1];
    await page.goto("/subjects");
    await settled(page);
    await expect(page.getByText("Sinh học QA").first()).toBeVisible();
    noProblems();
  });

  test("upload a PDF: it is stored, read, and the syllabus appears", async () => {
    test.setTimeout(180_000);
    await page.goto(`/subjects/${subjectId}/upload`);
    await settled(page);
    await page.locator("input[type=file]").first().setInputFiles(PDF);
    await expect(page.getByText("biology.pdf")).toBeVisible();
    await page.goto(`/subjects/${subjectId}/syllabus`);
    await expect(page.getByText("Chapter 1: Photosynthesis").first()).toBeVisible({ timeout: 120_000 });
    await expect(page.getByText("Chapter 3: Cell division").first()).toBeVisible();
    await page.goto(`/subjects/${subjectId}/documents`);
    await expect(page.getByText("biology").first()).toBeVisible();
    noProblems();
  });

  test("syllabus and graph views load; reload keeps them", async () => {
    await page.goto(`/subjects/${subjectId}/syllabus`);
    await settled(page);
    await page.getByRole("button", { name: "Mở hết" }).click();
    await page.reload();
    await settled(page);
    await expect(page.getByText("Chapter 2: Cellular respiration").first()).toBeVisible();
    await page.goto(`/subjects/${subjectId}/graph`);
    await expect(page.locator("main")).toBeVisible();
    await page.goto("/graph");
    await expect(page.locator("main")).toBeVisible();
    noProblems();
  });

  test("session: empty record is refused, a record is saved, finishing makes a card in the Kho", async () => {
    test.setTimeout(240_000);
    await page.goto(`/subjects/${subjectId}`);
    await settled(page);
    await page.getByText("Vào buổi học").first().click();
    await page.waitForURL(/\/sessions\/[0-9a-f-]{36}/);
    await settled(page);
    const record = page.getByRole("button", { name: "Ghi lại", exact: true });
    await record.click(); // nothing typed
    await expect(page.getByText("Chưa ghi lại lần nào")).toBeVisible();

    await page
      .locator("textarea")
      .fill(
        "Photosynthesis: light reactions make ATP and NADPH in the thylakoid; the Calvin cycle fixes CO2 into sugar using RuBisCO in the stroma.",
      );
    await record.dblclick(); // double submit: one record
    await expect(page.getByText("Đã ghi lại 1 lần")).toBeVisible();
    await page.reload(); // reload mid-flow keeps the record
    await settled(page);
    await expect(page.getByText("Đã ghi lại 1 lần")).toBeVisible();

    await page.getByRole("button", { name: "Kết thúc buổi học" }).click();
    await expect(page.getByText("thẻ đang được chuẩn bị")).toBeVisible();
    noProblems();

    // The AI makes the cards; the Kho lists them when ready.
    await expect(async () => {
      await page.goto("/kho-kien-thuc");
      await expect(page.locator("main")).toContainText("1 thẻ");
    }).toPass({ timeout: 150_000, intervals: [5_000] });
  });

  test("Kho: open the subject, edit a card (saved after reload), cancel and confirm delete", async () => {
    await page.goto(`/kho-kien-thuc?subject=${subjectId}`);
    await settled(page);
    await page.getByRole("link").filter({ hasText: /thẻ/ }).first().click();
    await settled(page);
    const card = page.locator("[data-slot=vault-card]").first();
    await expect(card).toBeVisible();
    await card.getByRole("button", { name: "Nguồn" }).click();
    await card.getByRole("button", { name: "Nguồn" }).click();
    await card.getByRole("button", { name: "Sửa thẻ" }).click();
    await card.getByLabel("Tiêu đề thẻ").fill("Quang hợp QA");
    await card.getByRole("button", { name: "Lưu" }).click();
    await expect(card.getByRole("heading", { name: "Quang hợp QA" })).toBeVisible();
    await page.reload();
    await settled(page);
    await expect(page.getByRole("heading", { name: "Quang hợp QA" })).toBeVisible();

    // an empty title cannot be saved
    await page.getByRole("button", { name: "Sửa thẻ" }).first().click();
    await page.getByLabel("Tiêu đề thẻ").fill("  ");
    await expect(page.getByRole("button", { name: "Lưu", exact: true })).toBeDisabled();
    await page.getByRole("button", { name: "Hủy", exact: true }).click();

    await page.getByRole("button", { name: "Sửa thẻ" }).first().click();
    await page.getByRole("button", { name: "Xóa thẻ" }).click();
    await page.getByRole("button", { name: "Giữ thẻ" }).click();
    await expect(page.getByLabel("Tiêu đề thẻ")).toHaveValue("Quang hợp QA");
    await page.getByRole("button", { name: "Xóa thẻ" }).click();
    await page.getByRole("button", { name: "Xóa hẳn thẻ" }).click();
    await expect(page.getByText("Quang hợp QA")).toHaveCount(0);
    await page.reload();
    await settled(page);
    await expect(page.getByText("Quang hợp QA")).toHaveCount(0);
    noProblems();
  });

});
