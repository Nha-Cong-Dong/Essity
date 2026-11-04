// T7.14 (US-15 AC6; US-02 AC1, AC14; US-03 AC1): the v2 learning loop on the screens a
// browser can reach without core-api: Gợi ý cho hôm nay -> the session screen (a sentence, then a
// note photo) -> the cards that went straight into the Kho (CARDS-V3: no draft review, no Lưu).
// The next-day Ôn step lives in core-api's tests/drafts/test_t714_learning_loop.py (real API and database). One stateful in-memory core answers web's /api routes for the
// whole loop, so a step that forgets the previous one fails here.
//
// Not reachable in CI (server components that call core-api): create subject, textbook upload and the
// syllabus; the real-stack self-test covers them (.work/T7.14/shots). Today v2 is shown through its
// fixture state "review".
import { expect, type Page, type Route, test } from "@playwright/test";

import { settled } from "./ready";

const SUBJECT = "0b8f1d2e-0000-4000-8000-000000000001";
const SESSION = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const FIRST_DAY = new Date("2026-11-02T09:00:00+07:00");

/** One fake core: a clock, the suggestion rule, the submission and its cards, and what Lưu stored. */
async function fakeCore(page: Page) {
  const state = { now: FIRST_DAY, studied: false, submitted: [] as unknown[], complete: false, uploads: 0 };
  const day = () => state.now.toISOString().slice(0, 10);
  const pace = { remaining_leaves: 5, days_left: 20, remaining_weight: 5, unit: null, text: "Còn 5 phần, 20 ngày: ổn." };
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, json: body });

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const body = request.postData() ? JSON.parse(request.postData() as string) : undefined;
    const path = url.pathname;
    if (path === `/api/subjects/${SUBJECT}/suggestion`) {
      const suggestion = {
        kind: "next_leaf",
        subject_id: SUBJECT,
        subject_name: "Mạng máy tính",
        section_id: "s32",
        section_title: state.studied ? "3.3 Điều khiển tắc nghẽn" : "3.2 Điều khiển luồng",
        reason: "Phần kế tiếp trong giáo trình.",
        pace,
        partial: false,
        remaining: 5,
        unit: null,
      };
      return json(route, { suggestion, today: day() });
    }
    if (path === `/api/sessions/${SESSION}/notes/upload-url`) {
      state.uploads += 1;
      return json(route, { url: "/storage-fake", method: "PUT", headers: {}, expires_at: "2099-01-01T00:00:00Z" }, 201);
    }
    if (path === `/api/sessions/${SESSION}/pieces`) {
      if (request.method() === "POST") {
        state.submitted.push(body);
        return json(route, { id: `p${state.submitted.length}`, position: state.submitted.length - 1, text: body.text, file_count: body.files.length, created_at: "2026-11-04T00:00:00Z" }, 201);
      }
      return json(route, { pieces: [], submitted: state.complete });
    }
    if (path === `/api/sessions/${SESSION}/complete`) {
      state.complete = true;
      return json(route, { submission_id: "s", session_id: SESSION, status: "queued", mentions: [] }, 201);
    }
    if (path === `/api/sessions/${SESSION}/result`) {
      const ready = state.complete;
      state.studied = ready;
      return json(route, { session_id: SESSION, submission_status: ready ? "done" : "processing", title: ready ? "Cửa sổ trượt" : null, cards: ready ? 2 : 0, notice: null });
    }
    return json(route, { error: "unavailable" }, 503);
  });
  return state;
}

test("the loop: suggestion, sentence, photo, cards in the Kho", async ({ page }) => {
  const core = await fakeCore(page);
  await page.setViewportSize({ width: 390, height: 900 });

  // 1. The subject block suggests the next section (US-15 AC6).
  await page.clock.setFixedTime(core.now);
  expect((await page.goto("/design-preview/subject-live?state=not-suggested"))?.status()).toBe(200);
  await settled(page);
  await page.getByRole("button", { name: "Gợi ý cho hôm nay" }).click();
  await expect(page.getByText("Nội dung hôm nay", { exact: true })).toBeVisible();

  // 2. The session: a sentence, then a note photo; the cards go into the Kho (US-02 AC1).
  expect((await page.goto("/design-preview/session-live"))?.status()).toBe(200);
  await settled(page);
  await page.route("**/storage-fake", (route) => route.fulfill({ status: 200 }));
  await page.getByRole("combobox").fill("Hôm nay học cửa sổ trượt.");
  await page.getByLabel("Chọn file bài nộp").setInputFiles({
    name: "vo-trang-1.png",
    mimeType: "image/png",
    buffer: Buffer.from("abc"),
  });
  await expect(page.getByText("Đã tải", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Ghi lại" }).click();
  await expect(page.getByText("Đã học trong buổi")).toBeVisible();
  await page.getByRole("button", { name: "Hoàn thành" }).click();
  await expect(page.getByText("Đã thêm 2 thẻ vào Kho.").first()).toBeVisible({ timeout: 15_000 });
  expect(core.uploads).toBe(1);
  expect(core.submitted).toEqual([
    {
      text: "Hôm nay học cửa sổ trượt.",
      mentions: [],
      files: [{ sha256: "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", mime: "image/png", size_bytes: 3 }],
    },
  ]);

  // 3. The confirmation names the session and leads to the Kho (CARDS-V3).
  await expect(page.getByText("Buổi học: Cửa sổ trượt")).toBeVisible();
  await expect(page.getByRole("link", { name: "Xem trong Kho kiến thức" })).toBeVisible();

  // 4. Not asserted here: "the card is in Ôn on the next learning day" is proven against the
  // real API and database in services/core-api/tests/drafts/test_t714_learning_loop.py (US-02b AC12,
  // US-03 AC4). A mocked card that sets `due` itself would prove nothing.
});
