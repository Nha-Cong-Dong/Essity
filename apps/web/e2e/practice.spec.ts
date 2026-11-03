// T8.7a (US-16, US-17; DESIGN §6.12): the Luyện tập screen at four widths. Geometry only. The
// busiest state has one unbroken long type name.
import { expect, type Locator, type Page, type Route, test } from "@playwright/test";

import { settled } from "./ready";

const WIDTHS = [320, 390, 768, 1440];
const STATES = [
  "home", "imported", "no-bank", "importing", "empty-ready", "candidates", "no-candidates", "quota",
  "removed", "result", "loading", "error",
];

type Box = { x: number; y: number; width: number; height: number };

async function box(locator: Locator): Promise<Box> {
  const found = await locator.boundingBox();
  if (found === null) throw new Error("no box");
  return found;
}

const inside = (inner: Box, outer: Box) =>
  inner.x >= outer.x - 0.5 &&
  inner.x + inner.width <= outer.x + outer.width + 0.5;

async function open(page: Page, width: number, path: string) {
  await page.setViewportSize({ width, height: 900 });
  expect((await page.goto(path))?.status()).toBe(200);
  await settled(page);
}

const noSideScroll = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

for (const width of WIDTHS) {
  test.describe(`practice @${width}px`, () => {
    // Red when: a long type name or a row pushes the page wider than the screen (incl. 320 px).
    for (const state of STATES) {
      test(`US-16 AC1: ${state}: the page does not scroll sideways`, async ({ page }) => {
        await open(page, width, `/design-preview/practice?state=${state}`);
        expect(await noSideScroll(page)).toBe(true);
      });
    }

    // Red when: a row's contents (long summary, buttons) spill out of the column, or a button is under 44 px tall.
    test("US-16 AC3: home: every row keeps its contents in the column and buttons are tappable", async ({ page }) => {
      await open(page, width, "/design-preview/practice?state=home");
      const column = await box(page.locator("main h1"));
      for (const row of await page.locator("[data-question]").all()) {
        const outer = await box(row);
        expect(outer.x + outer.width).toBeLessThanOrEqual(width + 0.5);
        for (const child of await row.locator("p, a, button").all()) {
          expect(inside(await box(child), outer)).toBe(true);
        }
        for (const button of await row.locator("button, a[role=button]").all()) {
          expect((await box(button)).height).toBeGreaterThanOrEqual(43.5);
        }
      }
      expect(column.x).toBeGreaterThanOrEqual(0);
    });

    // Red when: the long type name breaks out of its section.
    test("US-16 AC2: home: the long type name wraps inside its section", async ({ page }) => {
      await open(page, width, "/design-preview/practice?state=home");
      const section = page.locator("section[aria-labelledby=g-g1]");
      expect(inside(await box(section.locator("h2")), await box(section))).toBe(true);
    });

    // Red when: the candidate sheet or its buttons spill sideways.
    test("US-17 AC5: candidates: the sheet keeps its contents inside", async ({ page }) => {
      await open(page, width, "/design-preview/practice?state=candidates");
      const sheet = page.locator("[data-candidates]");
      for (const child of await sheet.locator("h3, p, a, button").all()) {
        expect(inside(await box(child), await box(sheet))).toBe(true);
      }
    });
  });
}

test("US-16 AC3: remove puts focus on Hoàn tác and undo puts it back", async ({ page }) => {
  await open(page, 390, "/design-preview/practice?state=home");
  await page.locator("[data-question=q12]").getByRole("button", { name: "Gỡ khỏi luyện tập" }).click();
  await expect(page.getByRole("button", { name: "Hoàn tác" })).toBeFocused();
  await page.getByRole("button", { name: "Hoàn tác" }).click();
  await expect(page.locator("[data-question=q12]").getByRole("button", { name: "Làm câu này" })).toBeFocused();
});

// --- T8.7: the real screen (PracticeLive) with web's /api/practice routes answered here.
const LIVE = "/design-preview/practice-live";
const Q1 = "0b8f1d2e-0000-4000-8000-0000000000a1";
const Q2 = "0b8f1d2e-0000-4000-8000-0000000000a2";
const ATTEMPT = "0b8f1d2e-0000-4000-8000-0000000000b1";

type Seen = { opened: string[]; submitted: Record<string, unknown>[]; removed: string[]; restored: number };

async function fakePractice(page: Page): Promise<Seen> {
  const seen: Seen = { opened: [], submitted: [], removed: [], restored: 0 };
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, json: body });
  await page.route("**/api/practice/**", async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    const open = /\/questions\/([0-9a-f-]{36})\/open$/.exec(pathname);
    if (open) {
      seen.opened.push(open[1]);
      return json(route, {
        attempt_id: ATTEMPT, status: "draft", answer_text: "", dont_remember: false, failure: null, grading: null,
        question: { id: open[1], prompt: "So sánh TCP và UDP." }, result: null, submitted_at: null, timing_ok: null,
      });
    }
    if (pathname.endsWith("/draft")) return route.fulfill({ status: 204 });
    if (pathname.endsWith("/submit")) {
      seen.submitted.push(JSON.parse(request.postData() ?? "{}"));
      return json(route, {
        attempt_id: ATTEMPT, status: "submitted", answer_text: "TCP tin cậy hơn.", dont_remember: false, failure: null,
        grading: "graded", question: { id: Q1, prompt: "So sánh TCP và UDP." }, submitted_at: "2026-11-02T08:00:00Z", timing_ok: false,
        result: {
          grade_id: "0b8f1d2e-0000-4000-8000-0000000000e1", overall: "partial", missing: ["Nêu ảnh hưởng tới độ trễ."],
          units: [{ text: "Nêu độ tin cậy.", met: true }, { text: "Nêu ảnh hưởng tới độ trễ.", met: false }],
          reference_answer: "TCP tin cậy nhưng thêm độ trễ; UDP nhanh hơn.", answer_origin: "ai", differs_from_card_id: null,
        },
      });
    }
    const worthless = /\/questions\/([0-9a-f-]{36})\/worthless$/.exec(pathname);
    if (/\/questions\/[0-9a-f-]{36}\/restore$/.test(pathname)) {
      seen.restored += 1;
      return route.fulfill({ status: 204 });
    }
    if (worthless) {
      seen.removed.push(worthless[1]);
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({ status: 404 });
  });
  return seen;
}

// US-16 AC2, AC3, AC5, AC8. Red when: the flow list -> question -> result -> remove breaks, the
// hidden time is not sent, or the screen shows a red, a streak, a score board or a clock.
test("US-16 AC2 AC3 AC5 AC8: list, do a question, see what is missing, remove it", async ({ page }) => {
  const seen = await fakePractice(page);
  await open(page, 390, LIVE);
  // AC8: neutral words, "chưa đủ dữ liệu" for a type with under 3 answers.
  await expect(page.getByText("đúng 7 trên 10 lần gần nhất")).toBeVisible();
  await expect(page.getByText("chưa đủ dữ liệu").first()).toBeVisible();

  await page.locator(`[data-question="${Q1}"]`).getByRole("button", { name: "Làm câu này" }).click();
  expect(seen.opened).toEqual([Q1]);
  await page.getByLabel("Câu trả lời của bạn").fill("TCP tin cậy hơn.");
  // AC5: the tab goes hidden for a while; the browser reports it, the answer carries it.
  await page.evaluate(async () => {
    const set = (value: boolean) => {
      Object.defineProperty(document, "hidden", { configurable: true, get: () => value });
      document.dispatchEvent(new Event("visibilitychange"));
    };
    set(true);
    await new Promise((resolve) => setTimeout(resolve, 300));
    set(false);
  });
  await page.getByRole("button", { name: "Gửi" }).click();
  await expect(page.getByRole("list", { name: "theo từng ý" }).getByRole("listitem")).toHaveCount(2);
  await expect(page.getByText("Nêu ảnh hưởng tới độ trễ.").first()).toBeVisible();
  expect(seen.submitted).toHaveLength(1);
  expect(seen.submitted[0]).toMatchObject({ answer_text: "TCP tin cậy hơn.", dont_remember: false });
  expect(seen.submitted[0].hidden_ms).toBeGreaterThanOrEqual(250);
  await expect(page.getByText("đáp án do AI soạn")).toBeVisible();

  // No red, no score board, no streak, no clock (DESIGN §4; AC5). Only this screen's own pieces
  // are scanned for words: the rubric and reference answer are GradeResult's and the user's.
  const own = await page.locator("[data-practice-extras], button").allTextContents();
  expect(own.join(" ")).not.toMatch(/(?<!\p{L})(streak|chuỗi|xếp hạng|ranking|điểm số|bảng điểm)(?!\p{L})/iu);
  expect(await page.locator("time").count()).toBe(0);
  const reds = await page.locator("main *").evaluateAll((els) =>
    els.filter((el) => {
      const style = getComputedStyle(el);
      return [style.color, style.backgroundColor].some((c) => {
        const m = /rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?\)/.exec(c);
        return m !== null && Number(m[4] ?? 1) > 0.5 && Number(m[1]) > 200 && Number(m[2]) < 70 && Number(m[3]) < 70;
      });
    }).length,
  );
  expect(reds).toBe(0);

  await page.getByRole("button", { name: "Gỡ khỏi luyện tập" }).click();
  await expect(page.getByText("Đã gỡ khỏi luyện tập.")).toBeVisible();
  expect(seen.removed).toEqual([Q1]);
  await page.getByRole("button", { name: "Câu tiếp" }).click();
  await expect(page.locator(`[data-question="${Q2}"]`)).toBeVisible();
});

// US-16 AC3. Red when: removing a row from the list needs more than one tap.
test("US-16 AC3: remove from the list is one tap and the row turns into a one-line note", async ({ page }) => {
  const seen = await fakePractice(page);
  await open(page, 390, LIVE);
  await page.locator(`[data-question="${Q2}"]`).getByRole("button", { name: "Gỡ khỏi luyện tập" }).click();
  await expect(page.locator(`[data-removed="${Q2}"]`)).toContainText("Đã gỡ khỏi luyện tập.");
  expect(seen.removed).toEqual([Q2]);
  // T8.7b: Hoàn tác brings the row back.
  await page.locator(`[data-removed="${Q2}"]`).getByRole("button", { name: "Hoàn tác" }).click();
  await expect(page.locator(`[data-question="${Q2}"]`)).toBeVisible();
  expect(seen.restored).toBe(1);
});

for (const width of WIDTHS) {
  // Red when: the live list or the answer page pushes the page wider than the screen.
  test(`US-16 AC1: live list does not scroll sideways @${width}px`, async ({ page }) => {
    await open(page, width, LIVE);
    expect(await noSideScroll(page)).toBe(true);
  });
}
