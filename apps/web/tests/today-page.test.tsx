// T2.14, T7.13: /today feeds GET /v1/today (v2) to TodayV2Screen. today-v2-screen.test.tsx pins the screen; this
// pins the page: the session is checked first, and a failing /v1/today is a notice, not a guess
// and never a redirect (DESIGN.md §6.3, plan K4).
import { renderToReadableStream } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const me = { email: "a@example.com", email_verified: true, has_subjects: true };
let today: () => Promise<unknown>;
vi.mock("@/lib/session", () => ({ requireVerifiedSession: async () => me }));
vi.mock("@/lib/today", () => ({ getToday: () => today() }));
vi.mock("next/server", () => ({ connection: async () => undefined }));
vi.mock("@/components/account-menu", () => ({ AccountMenu: () => null }));
vi.mock("@/components/shells", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
}));

const { default: TodayPage } = await import("@/app/today/page");

async function html(): Promise<string> {
  const stream = await renderToReadableStream(<TodayPage />);
  await stream.allReady;
  return new Response(stream).text();
}

describe("/today page (T2.14)", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  // Red when: the page ignores /v1/today (a constant screen) or drops its state.
  it("draws what /v1/today answers", async () => {
    today = async () => ({
      learning_day: "2026-10-21",
      state: "rested",
      session: null,
      in_progress: null,
      backlog: null,
      next_day: "2026-10-22",
      practice: null,
      subjects: [{ id: "0b8f1d2e-0000-4000-8000-000000000001", name: "Mạng máy tính", exam_date: "2026-12-15", days_until_exam: 55 }],
      review: { items: [], minutes: 0, new_saved_today: false, next_due_day: "2026-10-22" },
      unfinished: [],
      next_study: {
        items: [
          {
            subject_id: "0b8f1d2e-0000-4000-8000-000000000001",
            subject_name: "Mạng máy tính",
            kind: "next_leaf",
            section_id: null,
            section_title: "3.2 TCP flow control",
            partial: false,
            remaining: null,
            unit: null,
            reason: "Mục chưa học đầu tiên trong đề cương.",
            pace: { remaining_leaves: 3, remaining_weight: 3, unit: null, days_left: 55, text: "còn 3 mục, 55 ngày" },
          },
        ],
        empty_reason: null,
        links: [],
      },
    });
    const markup = await html();
    expect(markup).toContain("Hôm nay không có thẻ hay câu đến hạn.");
    expect(markup).toContain("TCP flow control");
    expect(markup).toContain("Vào buổi học");
    expect(markup).toContain("còn 3 mục, 55 ngày");
    expect(markup).toContain("Chưa có câu sẵn sàng");
  });

  // Red when: a failing /v1/today throws to the error page or shows a made-up state.
  it("a failing /v1/today is the notice with Thử lại", async () => {
    today = async () => {
      throw new Error("core-api answered /v1/today with 500");
    };
    const markup = await html();
    expect(markup).toContain('role="alert"');
    expect(markup).toContain("Không tải được trang hôm nay.");
    expect(markup).toContain("Thử lại");
    expect(markup).not.toContain("Hôm nay không có thẻ");
  });
});
