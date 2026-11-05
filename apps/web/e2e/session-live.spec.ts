// T7.12 (US-02 AC1, AC14; CARDS-V3): the main flow of the study session on the screen the real
// page builds, with web's /api routes answered here (no core-api): the sentence, the result (the
// cards went straight into the Kho), "Học tiếp hay dừng?"; and a read with no card.
import { expect, type Page, type Route, test } from "@playwright/test";

import { settled } from "./ready";

const PAGE = "/design-preview/session-live";
const SESSION = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";

type Seen = { submitted: unknown[]; uploads: unknown[]; reads: number };

/** web's routes, answered by a small in-memory core-api. `cards` is what the finished read made. */
async function fakeCore(page: Page, { cards = 2 }: { cards?: number } = {}): Promise<Seen> {
  const seen: Seen = { submitted: [], uploads: [], reads: 0 };
  let submitted = false;
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, json: body });
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const body = request.postData() ? JSON.parse(request.postData() as string) : undefined;
    if (url.pathname === `/api/sessions/${SESSION}/notes/upload-url`) {
      seen.uploads.push(body);
      return json(route, { url: "/storage-fake", method: "PUT", headers: {}, expires_at: "2099-01-01T00:00:00Z" }, 201);
    }
    if (url.pathname === `/api/sessions/${SESSION}/pieces`) {
      if (request.method() === "POST") {
        seen.submitted.push(body);
        return json(route, { id: `p${seen.submitted.length}`, position: seen.submitted.length - 1, text: body.text, file_count: body.files.length, created_at: "2026-11-04T00:00:00Z" }, 201);
      }
      return json(route, { pieces: [], submitted });
    }
    if (url.pathname === `/api/sessions/${SESSION}/complete`) {
      submitted = true;
      return json(route, { submission_id: "s", session_id: SESSION, status: "queued", mentions: [] }, 201);
    }
    if (url.pathname === `/api/sessions/${SESSION}/result`) {
      seen.reads += 1;
      // The first answer says "still reading"; the next one is the result.
      const done = submitted && seen.reads > 1;
      return json(route, {
        session_id: SESSION,
        submission_status: done ? "done" : "processing",
        title: done && cards > 0 ? "Cửa sổ trượt" : null,
        cards: done ? cards : 0,
        notice: done && cards === 0 ? "no_content_found" : null,
      });
    }
    return json(route, { error: "unavailable" }, 503);
  });
  return seen;
}

async function open(page: Page, width = 390) {
  await page.setViewportSize({ width, height: 900 });
  expect((await page.goto(PAGE))?.status()).toBe(200);
  await settled(page);
}

async function sendSentence(page: Page) {
  await page.getByRole("combobox").fill("Hôm nay học cửa sổ trượt.");
  await page.getByRole("button", { name: "Ghi lại" }).click();
  await expect(page.getByText("Đã học trong buổi")).toBeVisible();
  await page.getByRole("button", { name: "Kết thúc buổi học" }).click();
  await expect(page.getByText("Đang chờ đọc bài nộp…")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Đã thêm vào Kho|Chưa có thẻ mới/ })).toBeVisible({ timeout: 15_000 });
}

test.describe("study session on the real screen", () => {
  // T7.19 F2. Red when: a session opened from a suggestion shows the free session (the section is lost),
  // or a session with no section stops saying it is free.
  test("opened from a suggestion it is for that section; without one it is free", async ({ page }) => {
    const SECTION = "5f0c0000-0000-4000-8000-000000000001";
    await page.setViewportSize({ width: 390, height: 900 });
    expect((await page.goto(`${PAGE}?section=${SECTION}`))?.status()).toBe(200);
    await settled(page);
    await expect(page.getByText("Nội dung học tập: 3.2 TCP flow control")).toBeVisible();
    await expect(page.getByText("Buổi học tự do")).toHaveCount(0);
    await page.goto(PAGE);
    await settled(page);
    await expect(page.getByText("Buổi học tự do")).toBeVisible();
  });

  // US-02 AC1, AC14; CARDS-V3. Red when: the sentence does not reach /pieces, the confirmation does
  // not say how many cards went into the Kho, or the screen does not end in "Học tiếp hay dừng?".
  test("main flow: sentence, cards in the Kho, Học tiếp hay dừng?", async ({ page }) => {
    const seen = await fakeCore(page);
    await open(page);
    await sendSentence(page);
    expect(seen.submitted).toEqual([{ text: "Hôm nay học cửa sổ trượt.", mentions: [], files: [] }]);
    await expect(page.getByText("Đã thêm 2 thẻ vào Kho.").first()).toBeVisible();
    await expect(page.getByText("Buổi học: Cửa sổ trượt")).toBeVisible();
    await expect(page.getByRole("link", { name: "Xem trong Kho kiến thức" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Học tiếp hay dừng?" })).toBeVisible();
  });

  // CARDS-V3. Red when: a read that found nothing is silent, or does not point to the outline.
  test("a read with no card says so and points to the outline", async ({ page }) => {
    await fakeCore(page, { cards: 0 });
    await open(page);
    await sendSentence(page);
    await expect(page.getByText("Chưa tìm thấy nội dung để làm thẻ.").first()).toBeVisible();
    await expect(page.getByRole("link", { name: "Chọn mục từ đề cương" })).toBeVisible();
  });

  // US-02 AC1, AC13 (T7.12c). Red when: a picked photo is not uploaded, the send leaves it out, the
  // wrong type is silent, or the result does not appear after a send made of a photo alone.
  test("a photo alone: upload, send, see the cards; a wrong type is told neutrally", async ({ page }) => {
    const seen = await fakeCore(page);
    await page.route("**/storage-fake", (route) => route.fulfill({ status: 200 }));
    await open(page);
    const input = page.getByLabel("Chọn file bài nộp");
    await input.setInputFiles([
      { name: "trang-1.png", mimeType: "image/png", buffer: Buffer.from("abc") },
      { name: "virus.exe", mimeType: "application/octet-stream", buffer: Buffer.from("x") },
    ]);
    await expect(page.getByText("Đã tải", { exact: true })).toBeVisible();
    await expect(page.getByText(/Định dạng này chưa dùng được/)).toBeVisible();
    await page.getByRole("button", { name: "Ghi lại" }).click();
  await expect(page.getByText("Đã học trong buổi")).toBeVisible();
  await page.getByRole("button", { name: "Kết thúc buổi học" }).click();
    await expect(page.getByText("Đã thêm 2 thẻ vào Kho.").first()).toBeVisible({ timeout: 15_000 });
    expect(seen.uploads).toHaveLength(1);
    expect(seen.submitted).toEqual([
      {
        text: "",
        mentions: [],
        files: [{ sha256: "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", mime: "image/png", size_bytes: 3 }],
      },
    ]);
  });

  // Layout. Red when: at 320 px the result screen scrolls sideways.
  test("320 px: the result screen does not scroll sideways", async ({ page }) => {
    await fakeCore(page);
    await open(page, 320);
    await sendSentence(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
});
