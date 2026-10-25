// ADR-0025, T2.3c: the header and the subject rows at narrow widths (risk register R44, R46).
// Geometry only, never screenshots (fonts differ between Linux and Windows). Each test is one rule
// at one width, measured after the fonts have loaded. The plan is
// docs/plans/t2.3c-narrow-layout.md (G10).
import { expect, type Locator, type Page, test } from "@playwright/test";

const PAGE = "/design-preview/subjects";
const ROWS = 6; // the fixture's subjects
const BASE = [320, 390, 768, 1440];
const HEADER = [...BASE, 359, 360]; // both sides of `max-[360px]:` (width < 360px)
const ROW = [...BASE, 639, 640]; // both sides of `sm` (width >= 40rem)
const NARROW = [320, 390]; // below `sm`
const SM = 640;

// Rules known to fail on the code before the fix: `test.fail` passes only while they still fail,
// so CI proves "red on the old code". Filled from a local run without it; C2 (header) and C3
// (rows) take their entries out (T2.3c plan G8, G10.4).
const KNOWN_RED = new Set<string>([
  "R44-b a long name wraps inside its column@1440",
  "R44-b a long name wraps inside its column@320",
  "R44-b a long name wraps inside its column@390",
  "R44-b a long name wraps inside its column@639",
  "R44-b a long name wraps inside its column@640",
  "R44-b a long name wraps inside its column@768",
  "R44-c each half of the date line is one line, under the name below sm, beside it from sm@320",
  "R44-c each half of the date line is one line, under the name below sm, beside it from sm@390",
  "R44-c each half of the date line is one line, under the name below sm, beside it from sm@639",
  "R44-d the cover lines up with the top of the name@320",
  "R44-d the cover lines up with the top of the name@390",
  "R44-e below sm the date line starts where the name starts@320",
  "R44-e below sm the date line starts where the name starts@390",
  "R44-e below sm the date line starts where the name starts@639",
  "R44-f at 200% text the rows still fit@390",
  "R44-h below sm Sửa stays on the first line, right of the name@320",
  "R44-h below sm Sửa stays on the first line, right of the name@390",
  "R44-h below sm Sửa stays on the first line, right of the name@639",
  "R46-a nav labels are not clipped@320",
  "R46-b logo, nav and account do not touch@320",
  "R46-d the current item is scrolled into view, the page is not@280",
  "R46-e without the web fonts, logo, nav and account do not touch@320",
  "R46-e without the web fonts, nav labels are not clipped@320",
  "page: no horizontal scroll@1440",
  "page: no horizontal scroll@320",
  "page: no horizontal scroll@359",
  "page: no horizontal scroll@360",
  "page: no horizontal scroll@390",
  "page: no horizontal scroll@639",
  "page: no horizontal scroll@640",
  "page: no horizontal scroll@768",
]);

type Box = { x: number; y: number; width: number; height: number };
const right = (b: Box) => b.x + b.width;
const bottom = (b: Box) => b.y + b.height;
const overlap = (a: Box, b: Box) =>
  a.x < right(b) - 0.5 && b.x < right(a) - 0.5 && a.y < bottom(b) - 0.5 && b.y < bottom(a) - 0.5;
const inside = (inner: Box, outer: Box) =>
  inner.x >= outer.x - 0.5 && inner.y >= outer.y - 0.5 && right(inner) <= right(outer) + 0.5 && bottom(inner) <= bottom(outer) + 0.5;

async function box(locator: Locator): Promise<Box> {
  const b = await locator.boundingBox();
  if (b === null) throw new Error(`no box for ${locator}`);
  return b;
}

async function open(page: Page, width: number, options: { blockFonts?: boolean } = {}) {
  if (options.blockFonts) await page.route(/\.woff2$/, (route) => route.abort());
  await page.setViewportSize({ width, height: 900 });
  const response = await page.goto(PAGE);
  expect(response?.status()).toBe(200);
  await page.evaluate(() => document.fonts.ready);
}

const nav = (page: Page) => page.getByRole("navigation", { name: "Chính" });
const logo = (page: Page) => page.locator("header").getByText("Essity", { exact: true });
const account = (page: Page) => page.getByRole("button", { name: "Tài khoản" });
const rows = (page: Page) => page.locator("main li");

/** The parts of one subject row: cover, name, the date line (two halves) and "Sửa". */
function parts(row: Locator) {
  const exam = row.getByText(/^thi \d{2}\/\d{2}\/\d{4}$/);
  return {
    cover: row.locator('span[aria-hidden="true"]').first(),
    name: row.locator('[id$="-name"]'),
    date: exam.locator("xpath=.."),
    halves: exam.locator("xpath=../span"),
    edit: row.getByRole("button", { name: /^Sửa / }),
  };
}

function rule(name: string, widths: number[], body: (page: Page, width: number) => Promise<void>, options: { blockFonts?: boolean } = {}) {
  for (const width of widths) {
    test(`${name} @ ${width}px`, async ({ page }) => {
      test.fail(KNOWN_RED.has(`${name}@${width}`), "R44/R46 on the old code: removed with the fix (C2/C3)");
      await open(page, width, options);
      await body(page, width);
    });
  }
}

// --- Smoke: never marked as failing. The fixture renders, hydrates and breaks no CSP rule, so a
// failing rule above is about layout, not a broken page.
test("smoke: the fixture renders, hydrates and breaks no CSP rule", async ({ page }) => {
  const problems: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(message.text());
  });
  page.on("pageerror", (error) => problems.push(error.message));
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (event) => {
      console.error(`CSP violation: ${event.violatedDirective} ${event.blockedURI}`);
    });
  });
  await open(page, 390);
  await expect(rows(page)).toHaveCount(ROWS);
  await expect(nav(page).getByRole("link")).toHaveText(["Hôm nay", "Môn học"]);
  // Hydrated: "Sửa" opens the edit form only once React runs.
  await page.getByRole("button", { name: "Sửa Mạng máy tính" }).click();
  await expect(page.getByLabel("Môn")).toBeVisible();
  expect(problems).toEqual([]);
});

// --- Whole page
rule("page: no horizontal scroll", [...new Set([...HEADER, ...ROW])], async (page) => {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

// --- Header (R46)
const headerFits = async (page: Page) => {
  expect(await nav(page).evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
};
const headerApart = async (page: Page) => {
  const [l, n, a] = [await box(logo(page)), await box(nav(page)), await box(account(page))];
  expect(right(l)).toBeLessThanOrEqual(n.x + 0.5);
  expect(right(n)).toBeLessThanOrEqual(a.x + 0.5);
  for (const pill of await nav(page).getByRole("link").all()) expect(inside(await box(pill), n)).toBe(true);
};
rule("R46-a nav labels are not clipped", HEADER, headerFits);
rule("R46-b logo, nav and account do not touch", HEADER, headerApart);
rule("R46-c the logo keeps its size", [320, 359], async (page) => {
  const size = await logo(page).evaluate((el) => getComputedStyle(el).fontSize);
  await page.setViewportSize({ width: 1440, height: 900 });
  expect(await logo(page).evaluate((el) => getComputedStyle(el).fontSize)).toBe(size);
});
rule("R46-e without the web fonts, nav labels are not clipped", [320], headerFits, { blockFonts: true });
rule("R46-e without the web fonts, logo, nav and account do not touch", [320], headerApart, { blockFonts: true });
// 280 on purpose: the only width where two nav items must scroll, so it checks scrollIntoView
// brings the current one into view without scrolling the page (it does not replace the 320 rule).
rule("R46-d the current item is scrolled into view, the page is not", [280], async (page) => {
  const current = nav(page).locator('[aria-current="page"]');
  await expect(async () => {
    expect(inside(await box(current), await box(nav(page)))).toBe(true);
  }).toPass();
  expect(await page.evaluate(() => [window.scrollX, window.scrollY])).toEqual([0, 0]);
});

// --- Subject rows (R44)
async function eachRow(page: Page, check: (row: ReturnType<typeof parts>, li: Locator) => Promise<void>) {
  await expect(rows(page)).toHaveCount(ROWS);
  for (const li of await rows(page).all()) await check(parts(li), li);
}

rule("R44-a name, date and Sửa do not overlap", ROW, async (page) => {
  await eachRow(page, async ({ name, date, edit }, li) => {
    const [n, d, e, row] = [await box(name), await box(date), await box(edit), await box(li)];
    expect(overlap(n, d) || overlap(n, e) || overlap(d, e)).toBe(false);
    for (const part of [n, d, e]) expect(inside(part, row)).toBe(true);
  });
});
rule("R44-b a long name wraps inside its column", ROW, async (page) => {
  await eachRow(page, async ({ name }) => {
    expect(await name.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
  });
});
rule("R44-c each half of the date line is one line, under the name below sm, beside it from sm", ROW, async (page, width) => {
  await eachRow(page, async ({ name, date, halves }) => {
    for (const half of await halves.all()) {
      const lines = await half.evaluate((el) => el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight));
      expect(lines).toBeLessThan(1.5);
    }
    const [n, d] = [await box(name), await box(date)];
    if (width < SM) expect(d.y).toBeGreaterThanOrEqual(bottom(n) - 0.5);
    else expect(d.x).toBeGreaterThanOrEqual(right(n) - 0.5);
  });
});
rule("R44-d the cover lines up with the top of the name", NARROW, async (page) => {
  await eachRow(page, async ({ cover, name }) => {
    expect(Math.abs((await box(cover)).y - (await box(name)).y)).toBeLessThanOrEqual(2);
  });
});
rule("R44-e below sm the date line starts where the name starts", [...NARROW, 639], async (page) => {
  await eachRow(page, async ({ name, date }) => {
    expect(Math.abs((await box(date)).x - (await box(name)).x)).toBeLessThanOrEqual(1);
  });
});
rule("R44-h below sm Sửa stays on the first line, right of the name", [...NARROW, 639], async (page) => {
  await eachRow(page, async ({ name, edit }) => {
    const [n, e] = [await box(name), await box(edit)];
    expect(Math.abs(e.y - n.y)).toBeLessThanOrEqual(2);
    expect(e.x).toBeGreaterThanOrEqual(right(n) - 0.5);
  });
});
// The words of the title, not the h1 (a block as wide as the column, which "Tạo môn" sits in).
const titleText = (page: Page) => page.getByRole("heading", { level: 1 }).getByText("Môn học", { exact: true });
rule("R44-i the title and Tạo môn do not overlap", NARROW, async (page) => {
  const title = titleText(page);
  const create = page.getByText("Tạo môn", { exact: true });
  expect(overlap(await box(title), await box(create))).toBe(false);
});

// Text at 200%: the type scale is px and @theme inline writes it into each utility, so the classes
// themselves are overridden (T2.3c plan G10.1), and the precondition proves it took.
const DOUBLE = [".text-small{font-size:28px!important}", ".text-body{font-size:32px!important}", ".text-section{font-size:44px!important}", ".text-logo{font-size:48px!important}", ".text-title{font-size:72px!important}"].join("");
rule("R44-f at 200% text the rows still fit", [390], async (page) => {
  await page.addStyleTag({ content: DOUBLE });
  await page.evaluate(() => document.fonts.ready);
  const first = parts(rows(page).first());
  expect(await first.name.evaluate((el) => getComputedStyle(el).fontSize)).toBe("44px");
  await eachRow(page, async ({ name, date, halves, edit }) => {
    for (const half of await halves.all()) {
      const lines = await half.evaluate((el) => el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight));
      expect(lines).toBeLessThan(1.5);
    }
    const [n, d, e] = [await box(name), await box(date), await box(edit)];
    expect(overlap(n, d) || overlap(n, e) || overlap(d, e)).toBe(false);
  });
  expect(overlap(await box(titleText(page)), await box(page.getByText("Tạo môn", { exact: true })))).toBe(false);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
