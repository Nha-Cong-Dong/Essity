// T7.12 (US-02 AC1, AC14; US-02b AC6-AC9): the main flow of the study session on the screen the
// real page builds, with web's /api routes answered here (no core-api): the sentence, the cards,
// an edit, Lưu, "Học tiếp hay dừng?"; and the 409 "thẻ đã đổi ở nơi khác".
import { expect, type Page, type Route, test } from "@playwright/test";

import { settled } from "./ready";

const PAGE = "/design-preview/session-live";
const SESSION = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";

type Card = { id: string; title: string; content: string; version: number; status: string };

const core = (card: Card) => ({
  ...card,
  session_id: SESSION,
  kind: "concept",
  section_ids: [],
  anchors: [],
  revisions: [{ rev: 0, origin: "ai", content: {} }],
});

type Seen = { submitted: unknown[]; uploads: unknown[]; edits: { id: string; body: unknown }[]; saves: unknown[]; reads: number };

/** web's routes, answered by a small in-memory core-api. `stale` makes every edit a 409. */
async function fakeCore(page: Page, { stale = false }: { stale?: boolean } = {}): Promise<Seen> {
  const cards: Card[] = [
    { id: "11111111-1111-4111-8111-111111111111", title: "Cửa sổ trượt", content: "Bên gửi giữ rwnd.", version: 1, status: "draft" },
    { id: "22222222-2222-4222-8222-222222222222", title: "Cửa sổ nhận bằng 0", content: "Bên gửi dừng và thăm dò.", version: 1, status: "draft" },
  ];
  const seen: Seen = { submitted: [], uploads: [], edits: [], saves: [], reads: 0 };
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
    if (url.pathname === "/api/submissions") {
      submitted = true;
      seen.submitted.push(body);
      return json(route, { submission_id: "s", session_id: SESSION, status: "queued", mentions: [] }, 201);
    }
    if (url.pathname === `/api/sessions/${SESSION}/drafts` && request.method() === "GET") {
      seen.reads += 1;
      // The first answer says "still reading"; the next one has the cards.
      const done = submitted && seen.reads > 1;
      return json(route, { drafts: done ? cards.map(core) : [], submission_status: done ? "done" : "processing" });
    }
    if (url.pathname === `/api/sessions/${SESSION}/drafts/save`) {
      seen.saves.push(body);
      return json(route, { saved: body.units.map((u: { unit_id: string }) => u.unit_id) });
    }
    const one = /^\/api\/drafts\/([0-9a-f-]{36})$/.exec(url.pathname);
    if (one && request.method() === "PATCH") {
      seen.edits.push({ id: one[1], body });
      if (stale) return json(route, { error: "unit_changed_elsewhere" }, 409);
      const card = cards.find((c) => c.id === one[1]) as Card;
      card.title = body.title ?? card.title;
      card.content = body.content ?? card.content;
      card.version += 1;
      return json(route, core(card));
    }
    if (one && request.method() === "GET") {
      const card = cards.find((c) => c.id === one[1]) as Card;
      return json(route, core({ ...card, content: "Bản mới từ nơi khác", version: card.version + 4 }));
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
  await page.getByRole("button", { name: "Gửi" }).click();
  await expect(page.getByText("Đang chờ đọc bài nộp…")).toBeVisible();
  await expect(page.getByRole("button", { name: "Đúng rồi, lưu" })).toBeVisible({ timeout: 15_000 });
}

test.describe("study session on the real screen", () => {
  // US-02 AC1, AC14; US-02b AC6, AC7, AC9. Red when: the sentence does not reach /api/submissions, the
  // cards do not appear, an edit is not sent with the version it saw, Lưu does not send both cards
  // with their versions, or the screen does not end in "Học tiếp hay dừng?".
  test("main flow: sentence, cards, edit one, Lưu, Học tiếp hay dừng?", async ({ page }) => {
    const seen = await fakeCore(page);
    await open(page);
    await sendSentence(page);
    expect(seen.submitted).toEqual([{ session_id: SESSION, description: "Hôm nay học cửa sổ trượt.", mentions: [] }]);

    await page.getByRole("button", { name: "Sửa thẻ Cửa sổ trượt" }).click();
    await page.getByLabel("Nội dung thẻ Cửa sổ trượt").fill("Bên gửi giữ rwnd. Thêm ý mới.");
    await page.keyboard.press("Escape");
    await expect.poll(() => seen.edits.length, { timeout: 5_000 }).toBe(1);
    expect(seen.edits[0].body).toEqual({ version: 1, title: "Cửa sổ trượt", content: "Bên gửi giữ rwnd. Thêm ý mới." });

    await page.getByRole("button", { name: "Đúng rồi, lưu" }).click();
    await expect(page.getByRole("heading", { name: "Học tiếp hay dừng?" })).toBeVisible();
    expect(seen.saves).toEqual([
      {
        units: [
          { unit_id: "11111111-1111-4111-8111-111111111111", version: 2 },
          { unit_id: "22222222-2222-4222-8222-222222222222", version: 1 },
        ],
      },
    ]);
    await expect(page.getByText("Đã lưu 2 thẻ.")).toBeVisible();
  });

  // US-02 AC1, AC13 (T7.12c). Red when: a picked photo is not uploaded, the send leaves it out, the
  // wrong type is silent, or the cards do not appear after a send made of a photo alone.
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
    await page.getByRole("button", { name: "Gửi" }).click();
    await expect(page.getByRole("button", { name: "Đúng rồi, lưu" })).toBeVisible({ timeout: 15_000 });
    expect(seen.uploads).toHaveLength(1);
    expect(seen.submitted).toEqual([
      {
        session_id: SESSION,
        description: "",
        mentions: [],
        files: [{ sha256: "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", mime: "image/png", size_bytes: 3 }],
      },
    ]);
  });

  // US-02b AC7. Red when: a stale edit is silent, Lưu goes past it, or "Tải lại thẻ" does not bring the
  // other version and clear the notice.
  test("409: the card is told as changed elsewhere, Lưu waits, Tải lại thẻ brings the new text", async ({ page }) => {
    const seen = await fakeCore(page, { stale: true });
    await open(page);
    await sendSentence(page);
    await page.getByRole("button", { name: "Sửa thẻ Cửa sổ trượt" }).click();
    await page.getByLabel("Nội dung thẻ Cửa sổ trượt").fill("Chữ tôi vừa gõ.");
    await page.keyboard.press("Escape");
    await expect(page.getByText("Thẻ này đã đổi ở nơi khác.")).toBeVisible({ timeout: 5_000 });
    await page.getByRole("button", { name: "Đúng rồi, lưu" }).click();
    expect(seen.saves).toHaveLength(0);
    await page.getByRole("button", { name: "Tải lại thẻ" }).click();
    await expect(page.getByText("Bản mới từ nơi khác")).toBeVisible();
    await expect(page.getByText("Thẻ này đã đổi ở nơi khác.")).toHaveCount(0);
  });

  // US-02b AC6 / layout. Red when: at 320 px the cards screen scrolls sideways.
  test("320 px: the review screen does not scroll sideways", async ({ page }) => {
    await fakeCore(page);
    await open(page, 320);
    await sendSentence(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
});
