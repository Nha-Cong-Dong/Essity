// T7.14 (US-15 AC6; US-02 AC1, AC14; US-02b AC6-AC9; US-03 AC1): the v2 learning loop on the screens a
// browser can reach without core-api: Gợi ý cho hôm nay -> the session screen (a sentence, then a
// note photo) -> the draft cards -> Lưu. The next-day Ôn step lives in core-api's
// tests/drafts/test_t714_learning_loop.py (real API and database). One stateful in-memory core answers web's /api routes for the
// whole loop, so a step that forgets the previous one fails here.
//
// Not reachable in CI (server components that call core-api): create subject, textbook upload and the
// syllabus; the real-stack self-test covers them (.work/T7.14/shots). Today v2 is shown through its
// fixture state "review".
import { expect, type Page, type Route, test } from "@playwright/test";

import { settled } from "./ready";

const SUBJECT = "0b8f1d2e-0000-4000-8000-000000000001";
const SESSION = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const DAY_MS = 24 * 3600 * 1000;
const FIRST_DAY = new Date("2026-11-02T09:00:00+07:00");

type Stored = { unit_id: string; version: number; due: string };

/** One fake core: a clock, the suggestion rule, the submission and its cards, and what Lưu stored. */
async function fakeCore(page: Page) {
  const state = { now: FIRST_DAY, studied: false, submitted: [] as unknown[], uploads: 0, saved: [] as Stored[] };
  const day = () => state.now.toISOString().slice(0, 10);
  const nextDay = () => new Date(state.now.getTime() + DAY_MS).toISOString().slice(0, 10);
  const cards = [
    { id: "11111111-1111-4111-8111-111111111111", title: "Cửa sổ trượt", content: "Bên gửi giữ rwnd.", version: 1 },
    { id: "22222222-2222-4222-8222-222222222222", title: "Cửa sổ nhận bằng 0", content: "Bên gửi dừng và thăm dò.", version: 1 },
  ].map((c) => ({
    ...c,
    status: "draft",
    session_id: SESSION,
    kind: "concept",
    section_ids: [],
    anchors: [],
    revisions: [{ rev: 0, origin: "ai", content: {} }],
  }));
  const pace = { remaining_leaves: 5, days_left: 20, remaining_weight: 5, unit: null, text: "Còn 5 mục, 20 ngày: ổn." };
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
        reason: "Mục kế tiếp trong giáo trình.",
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
    if (path === "/api/submissions") {
      state.submitted.push(body);
      return json(route, { submission_id: "s", session_id: SESSION, status: "queued", mentions: [] }, 201);
    }
    if (path === `/api/sessions/${SESSION}/drafts` && request.method() === "GET") {
      const ready = state.submitted.length > 0;
      return json(route, { drafts: ready ? cards : [], submission_status: ready ? "done" : "processing" });
    }
    if (path === `/api/sessions/${SESSION}/drafts/save`) {
      for (const u of body.units as { unit_id: string; version: number }[]) {
        state.saved.push({ ...u, due: nextDay() });
      }
      state.studied = true;
      return json(route, { saved: body.units.map((u: { unit_id: string }) => u.unit_id) });
    }
    return json(route, { error: "unavailable" }, 503);
  });
  return state;
}

test("the loop: suggestion, sentence, photo, cards, Lưu", async ({ page }) => {
  const core = await fakeCore(page);
  await page.setViewportSize({ width: 390, height: 900 });

  // 1. The subject block suggests the next section (US-15 AC6).
  await page.clock.setFixedTime(core.now);
  expect((await page.goto("/design-preview/subject-live?state=not-suggested"))?.status()).toBe(200);
  await settled(page);
  await page.getByRole("button", { name: "Gợi ý cho hôm nay" }).click();
  await expect(page.getByText("Hôm nay nên học: mục 3.2")).toBeVisible();

  // 2. The session: a sentence, then a note photo; the cards come back (US-02 AC1).
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
  await page.getByRole("button", { name: "Gửi" }).click();
  await expect(page.getByRole("button", { name: "Đúng rồi, lưu" })).toBeVisible({ timeout: 15_000 });
  expect(core.uploads).toBe(1);
  expect(core.submitted).toEqual([
    {
      session_id: SESSION,
      description: "Hôm nay học cửa sổ trượt.",
      mentions: [],
      files: [{ sha256: "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", mime: "image/png", size_bytes: 3 }],
    },
  ]);

  // 3. Lưu stores both cards (US-02b AC6, AC9).
  await page.getByRole("button", { name: "Đúng rồi, lưu" }).click();
  await expect(page.getByText("Đã lưu 2 thẻ.")).toBeVisible();
  expect(core.saved.map((u) => u.unit_id)).toEqual([
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
  ]);

  // 4. Not asserted here: "the saved card is in Ôn on the next learning day" is proven against the
  // real API and database in services/core-api/tests/drafts/test_t714_learning_loop.py (US-02b AC12,
  // US-03 AC4). A mocked save that sets `due` itself would prove nothing.
});
